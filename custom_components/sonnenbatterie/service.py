import json

import aiohttp
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import async_get as dr_async_get
from homeassistant.util.read_only_dict import ReadOnlyDict
from timeofuse import TimeofUseSchedule

from custom_components.sonnenbatterie.const import (
    CONF_CHARGE_WATT,
    CONF_SERVICE_ITEM,
    CONF_SERVICE_SCHEDULE,
    CONF_SERVICE_VALUE,
    DOMAIN,
    LOGGER,
    SB_OPERATING_MODES,
    SB_OPERATING_MODES_NUM,
    SONNENBATTERIE_ISSUE_URL,
)
from custom_components.sonnenbatterie.coordinator import SonnenbatterieData


async def async_set_operating_mode(coordinator, mode: int) -> int:
    """Set the operating mode, with a readable error if the battery refuses.

    Writable according to sonnen: 1, 2, 10 and 11 (10 not in France, 2 not
    for sonnenBatterie 10 Hybrid, 11 only with newer firmware); no mode
    change at all while a virtual power plant (VPP) is active. The battery
    decides, so its answer is passed on instead of guessing the region here.
    """
    try:
        return await coordinator.async_call("set_operating_mode", mode)
    except aiohttp.ClientResponseError as e:
        if e.status == 401 or not 400 <= e.status < 500:
            # session expired or a server error (left after the retry):
            # passed on as is, the battery didn't refuse the mode
            raise
        raise HomeAssistantError(
            f"The battery refused operating mode {mode} (HTTP {e.status}). Mode changes "
            "are rejected while a virtual power plant (VPP) is active, and not every "
            "mode is available in every region or firmware version."
        ) from e


class SonnenbatterieService:
    def __init__(self, hass, config):
        self._hass = hass
        self._config = config

    def _get_coordinator(self, call_data: ReadOnlyDict, write: bool = True):
        return self._get_data(call_data, write).coordinator

    def _get_data(self, call_data: ReadOnlyDict, write: bool = True):
        """The runtime data of the battery the action is called for (the
        device_id), else of the entry that registered the actions."""
        LOGGER.debug(f"_get_data: {call_data}")
        if ATTR_DEVICE_ID in call_data:
            # no idea why, but sometimes it's a list and other times a str
            if isinstance(call_data[ATTR_DEVICE_ID], list):
                device_id = call_data[ATTR_DEVICE_ID][0]
            else:
                device_id = call_data[ATTR_DEVICE_ID]
            device_registry = dr_async_get(self._hass)
            if not (device_entry := device_registry.async_get(device_id)):
                raise HomeAssistantError(f"No device found for device_id: {device_id}")
            # DeviceEntry.config_entry_id since HA 2026.8, primary_config_entry
            # before (deprecated since 2026.10)
            entry_id = getattr(device_entry, "config_entry_id", None) or device_entry.primary_config_entry
            entry = self._hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN:
                raise HomeAssistantError(f"Unable to find config for device_id: {device_id} ({device_entry.name})")
        else:
            entry = self._config
        if not isinstance(data := getattr(entry, "runtime_data", None), SonnenbatterieData):
            raise HomeAssistantError(f"{entry.title} is not loaded. If it should be, please report an issue at {SONNENBATTERIE_ISSUE_URL}.")
        coordinator = data.coordinator
        if write and coordinator.is_slave:
            # read-only like its entities: the cascade's master controls it
            raise HomeAssistantError(
                f"{coordinator.name} is a cascade slave and is controlled by the cascade's "
                "master. Use the master's device instead.")
        return data

    # service definitions
    async def charge_battery(self, call: ServiceCall) -> ServiceResponse:
        LOGGER.debug(f"_charge_battery: {call.data}")
        power = int(call.data.get(CONF_CHARGE_WATT))
        power = max(power, 0)
        coordinator = self._get_coordinator(call.data)
        response = await coordinator.async_write_setpoint("number_charge", power)
        return {
            "charge": response,
        }

    async def discharge_battery(self, call: ServiceCall) -> ServiceResponse:
        LOGGER.debug(f"_discharge_battery: {call.data}")
        power = int(call.data.get(CONF_CHARGE_WATT))
        power = max(power, 0)
        coordinator = self._get_coordinator(call.data)
        response = await coordinator.async_write_setpoint("number_discharge", power)
        return {
            "discharge": response,
        }

    async def set_battery_reserve(self, call: ServiceCall) -> ServiceResponse:
        value = call.data.get(CONF_SERVICE_VALUE)
        coordinator = self._get_coordinator(call.data)
        response = int((await coordinator.async_write_setpoint("battery_reserve", value))["EM_USOC"])
        return {
            "battery_reserve": response,
        }

    async def set_config_item(self, call: ServiceCall) -> ServiceResponse:
        item = call.data.get(CONF_SERVICE_ITEM)
        value = call.data.get(CONF_SERVICE_VALUE)
        coordinator = self._get_coordinator(call.data)
        response = await coordinator.async_call("set_config_item", item, value)
        return {
            "response": response,
        }

    async def set_operating_mode(self, call: ServiceCall) -> ServiceResponse:
        mode = SB_OPERATING_MODES.get(call.data.get('mode'))
        coordinator = self._get_coordinator(call.data)
        response = await async_set_operating_mode(coordinator, mode)
        return {
            "mode": SB_OPERATING_MODES_NUM.get(str(response), "UNKNOWN")
        }

    async def set_operating_mode_num(self, call: ServiceCall) -> ServiceResponse:
        mode = call.data.get('mode')
        coordinator = self._get_coordinator(call.data)
        response = await async_set_operating_mode(coordinator, int(mode))
        return {
            "mode": response
        }

    async def set_tou_schedule(self, call: ServiceCall) -> ServiceResponse:
        schedule = call.data.get(CONF_SERVICE_SCHEDULE)
        try:
            json_schedule = json.loads(schedule)
        except ValueError as e:
            raise HomeAssistantError(f"Schedule is not a valid JSON string: '{schedule}'") from e

        data = self._get_data(call.data)
        for lp in range(len(json_schedule)):
            if json_schedule[lp]['threshold_p_max'] > data.tou_max:
                LOGGER.warning(f"Specified 'threshold_p_max' {json_schedule[lp]['threshold_p_max']} exceeds the "
                               f"battery's limit, capped to {data.tou_max}")
                json_schedule[lp]['threshold_p_max'] = data.tou_max

        tou = TimeofUseSchedule()
        try:
            tou.load_tou_schedule_from_json(json_schedule)
        except ValueError as e:
            raise HomeAssistantError(f"Schedule is not a valid schedule: '{schedule}'") from e
        except TypeError as t:
            raise HomeAssistantError(f"Schedule is not a valid schedule: '{schedule}'") from t

        # the capped schedule: the original string still has the values above the limit
        response = await data.coordinator.async_call("set_tou_schedule_string", json.dumps(json_schedule))
        return {
            "schedule": response["EM_ToU_Schedule"],
        }

    # noinspection PyUnusedLocal
    async def get_tou_schedule(self, call: ServiceCall) -> ServiceResponse:
        coordinator = self._get_coordinator(call.data, write=False)
        response = await coordinator.async_call("get_tou_schedule_string", write=False)
        return {
            "schedule": response,
        }

    # noinspection PyUnusedLocal
    async def get_battery_reserve(self, call: ServiceCall) -> ServiceResponse:
        coordinator = self._get_coordinator(call.data, write=False)
        response = await coordinator.async_call("get_battery_reserve", write=False)
        return {
            "backup_reserve": response,
        }

    async def get_operating_mode(self, call: ServiceCall) -> ServiceResponse:
        coordinator = self._get_coordinator(call.data, write=False)
        response = await coordinator.async_call("get_operating_mode", write=False)
        return {
            "operating_mode": SB_OPERATING_MODES_NUM.get(str(response), "UNKNOWN")
        }

    async def get_operating_mode_num(self, call: ServiceCall) -> ServiceResponse:
        coordinator = self._get_coordinator(call.data, write=False)
        response = await coordinator.async_call("get_operating_mode", write=False)
        return {
            "operating_mode": response,
        }
