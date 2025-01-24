import json

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import async_get as dr_async_get
from homeassistant.util.read_only_dict import ReadOnlyDict
from sonnenbatterie import AsyncSonnenBatterie
from timeofuse import TimeofUseSchedule

from custom_components.sonnenbatterie import CONF_COORDINATOR
from custom_components.sonnenbatterie.const import (
    CONF_CHARGE_WATT,
    CONF_SERVICE_ITEM,
    CONF_SERVICE_SCHEDULE,
    CONF_SERVICE_VALUE,
    DOMAIN,
    LOGGER,
    SB_OPERATING_MODES,
    SONNENBATTERIE_ISSUE_URL,
)


class SonnenbatterieService:
    def __init__(self, hass, config, coordinator):
        self._hass = hass
        self._config = config
        self._coordinator = coordinator

    def _get_sb_connection(self, call_data: ReadOnlyDict) -> AsyncSonnenBatterie:
        LOGGER.debug(f"_get_sb_connection: {call_data}")
        if ATTR_DEVICE_ID in call_data:
            # no idea why, but sometimes it's a list and other times a str
            if isinstance(call_data[ATTR_DEVICE_ID], list):
                device_id = call_data[ATTR_DEVICE_ID][0]
            else:
                device_id = call_data[ATTR_DEVICE_ID]
            device_registry = dr_async_get(self._hass)
            if not (device_entry := device_registry.async_get(device_id)):
                raise HomeAssistantError(f"No device found for device_id: {device_id}")
            if not (sb_config := self._hass.data[DOMAIN][device_entry.primary_config_entry]):
                raise HomeAssistantError(f"Unable to find config for device_id: {device_id} ({device_entry.name})")
            if sb_config.get(CONF_COORDINATOR):
                return sb_config.get("coordinator").sbconn
            else:
                raise HomeAssistantError(f"Invalid config for device_id: {device_id} ({sb_config}). Please report an issue at {SONNENBATTERIE_ISSUE_URL}.")
        else:
            return self._coordinator.sbconn

    # service definitions
    async def charge_battery(self, call: ServiceCall) -> ServiceResponse:
        LOGGER.debug(f"_charge_battery: {call.data}")
        power = int(call.data.get(CONF_CHARGE_WATT))
        if power < 0:
            power = 0
        # Make sure we have an sb2 object
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.charge_battery(power)
        # await sb_conn.logout()
        return {
            "charge": response,
        }

    async def discharge_battery(self, call: ServiceCall) -> ServiceResponse:
        LOGGER.debug(f"_discharge_battery: {call.data}")
        power = int(call.data.get(CONF_CHARGE_WATT))
        if power < 0:
            power = 0
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.discharge_battery(power)
        # await sb_conn.logout()
        return {
            "discharge": response,
        }

    async def set_battery_reserve(self, call: ServiceCall) -> ServiceResponse:
        value = call.data.get(CONF_SERVICE_VALUE)
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = int((await sb_conn.sb2.set_battery_reserve(value))["EM_USOC"])
        # await sb_conn.logout()
        return {
            "battery_reserve": response,
        }

    async def set_config_item(self, call: ServiceCall) -> ServiceResponse:
        item = call.data.get(CONF_SERVICE_ITEM)
        value = call.data.get(CONF_SERVICE_VALUE)
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.set_config_item(item, value)
        # await sb_conn.logout()
        return {
            "response": response,
        }

    async def set_operating_mode(self, call: ServiceCall) -> ServiceResponse:
        mode = SB_OPERATING_MODES.get(call.data.get('mode'))
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.set_operating_mode(mode)
        # await sb_conn.logout()
        return {
            "mode": response,
        }

    async def set_tou_schedule(self, call: ServiceCall) -> ServiceResponse:
        schedule = call.data.get(CONF_SERVICE_SCHEDULE)
        try:
            json_schedule = json.loads(schedule)
        except ValueError as e:
            raise HomeAssistantError(f"Schedule is not a valid JSON string: '{schedule}'") from e

        tou = TimeofUseSchedule()
        try:
            tou.load_tou_schedule_from_json(json_schedule)
        except ValueError as e:
            raise HomeAssistantError(f"Schedule is not a valid schedule: '{schedule}'") from e
        except TypeError as t:
            raise HomeAssistantError(f"Schedule is not a valid schedule: '{schedule}'") from t

        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.set_tou_schedule_string(schedule)
        # await sb_conn.logout()
        return {
            "schedule": response["EM_ToU_Schedule"],
        }

    # noinspection PyUnusedLocal
    async def get_tou_schedule(self, call: ServiceCall) -> ServiceResponse:
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.get_tou_schedule_string()
        # await sb_conn.logout()
        return {
            "schedule": response,
        }

    # noinspection PyUnusedLocal
    async def get_battery_reserve(self, call: ServiceCall) -> ServiceResponse:
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.get_battery_reserve()
        # await sb_conn.logout()
        return {
            "backup_reserve": response,
        }

    async def get_operating_mode(self, call: ServiceCall) -> ServiceResponse:
        sb_conn = self._get_sb_connection(call.data)
        # await sb_conn.login()
        response = await sb_conn.sb2.get_operating_mode()
        # await sb_conn.logout()
        return {
            "operating_mode": response,
        }
