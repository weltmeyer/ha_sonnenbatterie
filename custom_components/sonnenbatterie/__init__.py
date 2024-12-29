"""The Sonnenbatterie integration."""

import json
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    Platform
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse, SupportsResponse,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import HomeAssistantError
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
    LOGGER.info(f"setup_entry: {json.dumps(dict(config_entry.data))}\n{json.dumps(dict(config_entry.options))}")
    ip_address = config_entry.data["ip_address"]
    password = config_entry.data["password"]
    username = config_entry.data["username"]

    sb = AsyncSonnenBatterie(username, password, ip_address)
    await sb.login()
    inverter_power = int((await sb.get_batterysystem())['battery_system']['system']['inverter_capacity'])

    # noinspection PyPep8Naming
    SCHEMA_CHARGE_BATTERY = vol.Schema(
        {
            **cv.ENTITY_SERVICE_FIELDS,
            vol.Required(CONF_CHARGE_WATT): vol.Range(min=0, max=inverter_power),
        }
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, [ Platform.SENSOR ])
    # rustydust_241227: this doesn't seem to be needed
    # config_entry.add_update_listener(update_listener)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))


    # service definitions
    async def charge_battery(call: ServiceCall) -> ServiceResponse:
        power = int(call.data.get(CONF_CHARGE_WATT))
        # Make sure we have an sb2 object
        await sb.login()
        response = await sb.sb2.charge_battery(power)
        return {
            "charge": response,
        }

    async def discharge_battery(call: ServiceCall) -> ServiceResponse:
        power = int(call.data.get(CONF_CHARGE_WATT))
        await sb.login()
        response = await sb.sb2.discharge_battery(power)
        return {
            "discharge": response,
        }

    async def set_battery_reserve(call: ServiceCall) -> ServiceResponse:
        value = call.data.get(CONF_SERVICE_VALUE)
        await sb.login()
        response = int((await sb.sb2.set_battery_reserve(value))["EM_USOC"])
        return {
            "battery_reserve": response,
        }

    async def set_config_item(call: ServiceCall) -> ServiceResponse:
        item = call.data.get(CONF_SERVICE_ITEM)
        value = call.data.get(CONF_SERVICE_VALUE)
        await sb.login()
        response = await sb.sb2.set_config_item(item, value)
        return {
            "response": response,
        }

    async def set_operating_mode(call: ServiceCall) -> ServiceResponse:
        mode = SB_OPERATING_MODES.get(call.data.get('mode'))
        await sb.login()
        response = await sb.set_operating_mode(mode)
        LOGGER.info("set_operating_mode: " + json.dumps(response))
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

        await sb.login()
        response = await sb.sb2.set_tou_schedule_string(schedule)
        return {
            "schedule": response["EM_ToU_Schedule"],
        }

    async def get_tou_schedule(call: ServiceCall) -> ServiceResponse:
        await sb.login()
        response = await sb.sb2.get_tou_schedule_string()
        LOGGER.info("get_tou_schedule_string: " + response)
        return {
            "schedule": response,
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

    # Done setting up the entry
    return True

async def async_reload_entry(hass, entry):
     """Reload config entry."""
     await async_unload_entry(hass, entry)
     await async_setup_entry(hass, entry)

# rustydust_241227: this doesn't seem to be needed
# async def update_listener(hass, entry):
#     LOGGER.warning("Update listener" + json.dumps(dict(entry.options)))
#     # hass.data[DOMAIN][entry.entry_id]["monitor"].update_interval_seconds = (
#     #     entry.options.get(CONF_SCAN_INTERVAL)
#     # )


async def async_unload_entry(hass, entry):
    """Handle removal of an entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, Platform.SENSOR)
