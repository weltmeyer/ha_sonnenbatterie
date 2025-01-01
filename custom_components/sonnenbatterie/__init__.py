"""The Sonnenbatterie integration."""

import json

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    Platform,
    ATTR_DEVICE_ID,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse, SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    async_get as dr_async_get,
)
from homeassistant.util.read_only_dict import ReadOnlyDict
from sonnenbatterie import AsyncSonnenBatterie
from timeofuse import TimeofUseSchedule

from .const import *

# rustydust_241227: this doesn't seem to be needed - kept until we're sure ;)
# async def async_setup(hass, config):
#     """Set up a skeleton component."""
#     hass.data.setdefault(DOMAIN, {})
#     return True

SB_OPERATING_MODES = {
    "manual": 1,
    "automatic": 2,
    "expansion": 6,
    "timeofuse": 10
}


SCHEMA_SET_BATTERY_RESERVE = vol.Schema(
    {
        **cv.ENTITY_SERVICE_FIELDS,
        vol.Required(CONF_SERVICE_VALUE): vol.Range(min=0, max=100)
    }
)

SCHEMA_SET_CONFIG_ITEM = vol.Schema(
    {
        **cv.ENTITY_SERVICE_FIELDS,
        vol.Required(CONF_SERVICE_ITEM, default=""): vol.In(CONF_CONFIG_ITEMS),
        vol.Required(CONF_SERVICE_VALUE, default=""): str
    }
)

SCHEMA_SET_OPERATING_MODE = vol.Schema(
    {
        **cv.ENTITY_SERVICE_FIELDS,
        vol.Required(CONF_SERVICE_MODE, default="automatic"): vol.In(CONF_OPERATING_MODES),
    }
)

SCHEMA_SET_TOU_SCHEDULE_STRING = vol.Schema(
    {
        **cv.ENTITY_SERVICE_FIELDS,
        vol.Required(CONF_SERVICE_SCHEDULE): cv.string_with_no_html,
    }
)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    LOGGER.debug(f"setup_entry: {config_entry.data}\n{config_entry.entry_id}")
    ip_address = config_entry.data[CONF_IP_ADDRESS]
    password = config_entry.data[CONF_PASSWORD]
    username = config_entry.data[CONF_USERNAME]

    sb = AsyncSonnenBatterie(username, password, ip_address)
    await sb.login()
    inverter_power = int((await sb.get_batterysystem())['battery_system']['system']['inverter_capacity'])
    await sb.logout()

    # noinspection PyPep8Naming
    SCHEMA_CHARGE_BATTERY = vol.Schema(
        {
            **cv.ENTITY_SERVICE_FIELDS,
            vol.Required(CONF_CHARGE_WATT): vol.Range(min=0, max=inverter_power),
        }
    )

    # Set up base data in hass object
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {}
    hass.data[DOMAIN][config_entry.entry_id][CONF_IP_ADDRESS] = ip_address
    hass.data[DOMAIN][config_entry.entry_id][CONF_USERNAME] = username
    hass.data[DOMAIN][config_entry.entry_id][CONF_PASSWORD] = password

    await hass.config_entries.async_forward_entry_setups(config_entry, [ Platform.SENSOR ])
    # rustydust_241227: this doesn't seem to be needed
    # config_entry.add_update_listener(update_listener)
    # config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    def _get_sb_connection(call_data: ReadOnlyDict) -> AsyncSonnenBatterie:
        LOGGER.debug(f"_get_sb_connection: {call_data}")
        if ATTR_DEVICE_ID in call_data:
            # no idea why, but sometimes it's a list and other times a str
            if isinstance(call_data[ATTR_DEVICE_ID], list):
                device_id = call_data[ATTR_DEVICE_ID][0]
            else:
                device_id = call_data[ATTR_DEVICE_ID]
            device_registry = dr_async_get(hass)
            if not (device_entry := device_registry.async_get(device_id)):
                raise HomeAssistantError(f"No device found for device_id: {device_id}")
            if not (sb_config := hass.data[DOMAIN][device_entry.primary_config_entry]):
                raise HomeAssistantError(f"Unable to find config for device_id: {device_id} ({device_entry.name})")
            if not (sb_config.get(CONF_USERNAME) and sb_config.get(CONF_PASSWORD) and sb_config.get(CONF_IP_ADDRESS)):
                raise HomeAssistantError(f"Invalid config for device_id: {device_id} ({sb_config}). Please report an issue at {SONNENBATTERIE_ISSUE_URL}.")
            return AsyncSonnenBatterie(sb_config.get(CONF_USERNAME), sb_config.get(CONF_PASSWORD), sb_config.get(CONF_IP_ADDRESS))
        else:
            return sb

    # service definitions
    async def charge_battery(call: ServiceCall) -> ServiceResponse:
        power = int(call.data.get(CONF_CHARGE_WATT))
        # Make sure we have an sb2 object
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.charge_battery(power)
        await sb_conn.logout()
        return {
            "charge": response,
        }

    async def discharge_battery(call: ServiceCall) -> ServiceResponse:
        power = int(call.data.get(CONF_CHARGE_WATT))
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.discharge_battery(power)
        await sb_conn.logout()
        return {
            "discharge": response,
        }

    async def set_battery_reserve(call: ServiceCall) -> ServiceResponse:
        value = call.data.get(CONF_SERVICE_VALUE)
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = int((await sb_conn.sb2.set_battery_reserve(value))["EM_USOC"])
        await sb_conn.logout()
        return {
            "battery_reserve": response,
        }

    async def set_config_item(call: ServiceCall) -> ServiceResponse:
        item = call.data.get(CONF_SERVICE_ITEM)
        value = call.data.get(CONF_SERVICE_VALUE)
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.set_config_item(item, value)
        await sb_conn.logout()
        return {
            "response": response,
        }

    async def set_operating_mode(call: ServiceCall) -> ServiceResponse:
        mode = SB_OPERATING_MODES.get(call.data.get('mode'))
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.set_operating_mode(mode)
        await sb_conn.logout()
        return {
            "mode": response,
        }

    async def set_tou_schedule(call: ServiceCall) -> ServiceResponse:
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

        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.set_tou_schedule_string(schedule)
        await sb_conn.logout()
        return {
            "schedule": response["EM_ToU_Schedule"],
        }

    # noinspection PyUnusedLocal
    async def get_tou_schedule(call: ServiceCall) -> ServiceResponse:
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.get_tou_schedule_string()
        await sb_conn.logout()
        return {
            "schedule": response,
        }

    # noinspection PyUnusedLocal
    async def get_battery_reserve(call: ServiceCall) -> ServiceResponse:
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.get_battery_reserve()
        await sb_conn.logout()
        return {
            "backup_reserve": response,
        }

    async def get_operating_mode(call: ServiceCall) -> ServiceResponse:
        sb_conn = _get_sb_connection(call.data)
        await sb_conn.login()
        response = await sb_conn.sb2.get_operating_mode()
        await sb_conn.logout()
        return {
            "operating_mode": response,
        }

    # service registration
    hass.services.async_register(
        DOMAIN,
        "charge_battery",
        charge_battery,
        schema=SCHEMA_CHARGE_BATTERY,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "discharge_battery",
        discharge_battery,
        schema=SCHEMA_CHARGE_BATTERY,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "set_battery_reserve",
        set_battery_reserve,
        schema=SCHEMA_SET_BATTERY_RESERVE,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "set_config_item",
        set_config_item,
        schema=SCHEMA_SET_CONFIG_ITEM,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "set_operating_mode",
        set_operating_mode,
        schema=SCHEMA_SET_OPERATING_MODE,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "set_tou_schedule",
        set_tou_schedule,
        schema=SCHEMA_SET_TOU_SCHEDULE_STRING,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "get_tou_schedule",
        get_tou_schedule,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "get_battery_reserve",
        get_battery_reserve,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "get_operating_mode",
        get_operating_mode,
        supports_response=SupportsResponse.ONLY,
    )

    # Done setting up the entry
    return True

# rustydust_241230: no longer needed
# async def async_reload_entry(hass, entry):
#      """Reload config entry."""
#      await async_unload_entry(hass, entry)
#      await async_setup_entry(hass, entry)

# rustydust_241227: this doesn't seem to be needed
# async def update_listener(hass, entry):
#     LOGGER.warning("Update listener" + json.dumps(dict(entry.options)))
#     # hass.data[DOMAIN][entry.entry_id]["monitor"].update_interval_seconds = (
#     #     entry.options.get(CONF_SCAN_INTERVAL)
#     # )


async def async_unload_entry(hass, entry):
    """Handle removal of an entry."""
    LOGGER.debug(f"Unloading config entry: {entry}")
    return await hass.config_entries.async_forward_entry_unload(entry, Platform.SENSOR)
