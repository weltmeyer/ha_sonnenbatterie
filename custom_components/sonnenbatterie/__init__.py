"""The Sonnenbatterie integration."""
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_IP_ADDRESS
from homeassistant.core import (
    HomeAssistant, SupportsResponse,
)
from homeassistant.exceptions import ConfigEntryNotReady
from sonnenbatterie import AsyncSonnenBatterie

from .const import *
from .coordinator import SonnenbatterieCoordinator
from .sensor_list import SonnenbatterieSensorEntityDescription
from .service import SonnenbatterieService

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

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


async def _get_serial_number(config_entry: ConfigEntry) -> str:
    sb_conn = AsyncSonnenBatterie(config_entry.data.get(CONF_USERNAME),
                                  config_entry.data.get(CONF_PASSWORD),
                                  config_entry.data.get(CONF_IP_ADDRESS))
    await sb_conn.logout()
    sysdata = await sb_conn.get_systemdata()
    await sb_conn.logout()
    return sysdata.get("DE_Ticket_Number", "sru-unknown")

# noinspection PyUnusedLocal
async def async_setup(hass, config):
    """Set up using YAML is not supported by this integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    LOGGER.debug(f"setup_entry: {config_entry.data} | {config_entry.entry_id}")
    # only initialize if not already present
    if DOMAIN not in hass.data:
        hass.data.setdefault(DOMAIN, {})

    # Fix missing serial number
    serial_number = config_entry.data.get(CONF_SERIAL_NUMBER)
    if serial_number is None:
        LOGGER.debug("No serial number provided, trying to determine from Sonnenbatterie")
        serial_number = await _get_serial_number(config_entry)
        _config_data = config_entry.data.copy()
        _config_data[CONF_SERIAL_NUMBER] = serial_number
        hass.config_entries.async_update_entry(config_entry, data=_config_data)
        LOGGER.debug(f"serial_number: {serial_number}")

    # init the master coordinator
    sb_coordinator = SonnenbatterieCoordinator(hass, config_entry, serial_number)

    # calls SonnenbatterieCoordinator._async_update_data()
    await sb_coordinator.async_refresh()
    if not sb_coordinator.last_update_success:
        raise ConfigEntryNotReady
    else:
        await sb_coordinator.fetch_sonnenbatterie_on_startup()
    # save coordinator as early as possible
    hass.data[DOMAIN][config_entry.entry_id] = {}
    hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR] = sb_coordinator

    inverter_power = sb_coordinator.latestData['battery_system']['battery_system']['system']['inverter_capacity']

    # noinspection PyPep8Naming
    SCHEMA_CHARGE_BATTERY = vol.Schema(
        {
            **cv.ENTITY_SERVICE_FIELDS,
            vol.Required(CONF_CHARGE_WATT): vol.Range(min=0, max=inverter_power),
        }
    )

    # Initialize our services
    services = SonnenbatterieService(hass, config_entry, sb_coordinator)

    # Set up base data in hass object
    # hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id][CONF_INVERTER_MAX] = inverter_power

    # Setup our sensors, services and whatnot
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # service registration
    hass.services.async_register(
        DOMAIN,
        "charge_battery",
        services.charge_battery,
        schema=SCHEMA_CHARGE_BATTERY,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "discharge_battery",
        services.discharge_battery,
        schema=SCHEMA_CHARGE_BATTERY,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "set_battery_reserve",
        services.set_battery_reserve,
        schema=SCHEMA_SET_BATTERY_RESERVE,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "set_config_item",
        services.set_config_item,
        schema=SCHEMA_SET_CONFIG_ITEM,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "set_operating_mode",
        services.set_operating_mode,
        schema=SCHEMA_SET_OPERATING_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "set_tou_schedule",
        services.set_tou_schedule,
        schema=SCHEMA_SET_TOU_SCHEDULE_STRING,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "get_tou_schedule",
        services.get_tou_schedule,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "get_battery_reserve",
        services.get_battery_reserve,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        "get_operating_mode",
        services.get_operating_mode,
        supports_response=SupportsResponse.OPTIONAL,
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

