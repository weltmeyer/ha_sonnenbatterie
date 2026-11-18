"""The Sonnenbatterie integration."""
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import (
    HomeAssistant,
    SupportsResponse,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from sonnenbatterie import AsyncSonnenBatterie

from .const import *
from .coordinator import SonnenbatterieCoordinator, SonnenbatterieData
from .sensor_list import SENSORS
from .service import SonnenbatterieService

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# set up via config entries (UI) only, no configuration.yaml options
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

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

SCHEMA_SET_OPERATING_MODE_NUM = vol.Schema(
    {
        **cv.ENTITY_SERVICE_FIELDS,
        vol.Required(CONF_SERVICE_MODE, default=2): vol.In(CONF_OPERATING_MODES_NUM),
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

def _migrate_control_unique_ids(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Up to 2026.3.2 the numbers, the select and the buttons used their
    (wrongly prefixed) entity id as unique id: "sonnenbatterie.sonnenbatterie_
    <serial>_<key>". Since 2026.7.0 it is "sonnenbatterie_<serial>_<key>", so
    an update from an older version left the old entities behind as "no
    longer provided" and created new ones with new entity ids.

    Give the old entries the new unique id, so they are picked up again and
    keep their entity id, name and settings. If the new entity already exists
    (the update to 2026.7.0 or newer happened before this migration), both
    are left alone: the new one may be in use by now."""
    ent_reg = er.async_get(hass)
    old_prefix = f"{DOMAIN}.{DOMAIN}_"
    left_behind = []
    for entity in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id):
        if entity.domain not in (Platform.NUMBER, Platform.SELECT, Platform.BUTTON):
            continue
        if not entity.unique_id.startswith(old_prefix):
            continue
        new_unique_id = entity.unique_id.removeprefix(f"{DOMAIN}.")
        if ent_reg.async_get_entity_id(entity.domain, DOMAIN, new_unique_id):
            left_behind.append(entity.entity_id)
            continue
        LOGGER.info(f"{entity.entity_id}: migrating unique id to {new_unique_id}")
        ent_reg.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)
    if left_behind:
        LOGGER.info(
            "These entities from a version before 2026.7.0 are no longer provided, their "
            f"replacements already exist. They can be removed: {', '.join(sorted(left_behind))}")


def _remove_stale_slave_entities(hass: HomeAssistant, config_entry: ConfigEntry, serial: str) -> None:
    """A cascade's slave gets no controls, meters or cascade-wide sensors.
    Remove those an earlier version created for it, instead of leaving them
    behind as unavailable."""
    ent_reg = er.async_get(hass)
    skipped = {d.legacy_key or d.key for d in SENSORS if not d.on_slave}
    prefix = f"sensor.sonnenbatterie_{serial}_"
    for entity in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id):
        stale = entity.domain in (Platform.NUMBER, Platform.SELECT, Platform.BUTTON)
        if entity.domain == Platform.SENSOR and entity.unique_id.startswith(prefix):
            key = entity.unique_id[len(prefix):]
            stale = key in skipped or key.startswith("meter_")
        if stale:
            LOGGER.info(f"cascade slave {serial}: removing {entity.entity_id}")
            ent_reg.async_remove(entity.entity_id)


# noinspection PyUnusedLocal
async def async_setup(hass, config):
    """Set up using YAML is not supported by this integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _safe = {k: ("***" if k in (CONF_PASSWORD, CONF_AUTH_TOKEN) else v)
             for k, v in config_entry.data.items()}
    LOGGER.debug(f"setup_entry: {_safe} | {config_entry.entry_id}")

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
    # whole cascade's inverter power on a cascade master, see populate_battery_info()
    inverter_power = sb_coordinator.latestData['battery_info']['max_power']
    max_tou_power = sb_coordinator.latestData.get('commissioning_settings',{}).get('data', {}).get('attributes', {}).get('tou_max_power_limit', '22000')
    LOGGER.debug(f"inverter_power: {inverter_power}, tou_power: {max_tou_power}")
    config_entry.runtime_data = SonnenbatterieData(
        coordinator=sb_coordinator, inverter_max=int(inverter_power), tou_max=int(max_tou_power))

    # noinspection PyPep8Naming
    SCHEMA_CHARGE_BATTERY = vol.Schema(
        {
            **cv.ENTITY_SERVICE_FIELDS,
            # vol.Required(CONF_CHARGE_WATT): vol.Range(min=0, max=inverter_power),
            vol.Required(CONF_CHARGE_WATT): str,
        }
    )

    # Initialize our services
    services = SonnenbatterieService(hass, config_entry)

    # before the platforms look up their entities
    _migrate_control_unique_ids(hass, config_entry)

    if sb_coordinator.is_slave:
        _remove_stale_slave_entities(hass, config_entry, serial_number)

    # Setup our sensors, services and whatnot
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    if sb_coordinator.is_slave:
        # controlled by the cascade's master; registering the services here
        # would also point them at this slave
        LOGGER.info(f"cascade slave {serial_number} - read-only, no SERVICE functions")
    elif sb_coordinator.latestData.get('api_configuration',{}).get('IN_LocalAPIWriteActive', '0') == '1':
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
            "set_operating_mode_num",
            services.set_operating_mode_num,
            schema=SCHEMA_SET_OPERATING_MODE_NUM,
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

        hass.services.async_register(
            DOMAIN,
            "get_operating_mode_num",
            services.get_operating_mode_num,
            supports_response=SupportsResponse.OPTIONAL,
        )

    else:
        LOGGER.info("JSON-API write access not enabled - disabling SERVICE functions")

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
    """Handle removal of an entry.

    Unload ALL platforms (not only SENSOR): otherwise select/number/button stay
    loaded across a reload/reconfigure, and the next setup fails with
    'Config entry ... has already been setup!' — leaving the setpoint numbers
    missing.
    """
    LOGGER.debug(f"Unloading config entry: {entry}")
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # close the coordinator's HTTP session, otherwise every reload (e.g.
        # a cascade slave's new IP address) leaks one
        coordinator = entry.runtime_data.coordinator
        if coordinator is not None:
            try:
                await coordinator.sbconn.logout()
            except Exception:  # best effort
                LOGGER.debug("logout on unload failed", exc_info=True)
    return unloaded

