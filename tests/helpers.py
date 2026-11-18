"""Helpers shared by the tests."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie.const import DOMAIN

from .fake_battery import PASSWORD, FakeBattery


async def setup_battery(hass: HomeAssistant, battery: FakeBattery, username: str = "User",
                        password: str = PASSWORD) -> ConfigEntry:
    """Add the battery through the config flow, like a user would."""
    result = await user_flow(hass, battery, username, password)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return result["result"]


async def user_flow(hass: HomeAssistant, battery: FakeBattery, username: str = "User",
                    password: str = PASSWORD) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {
        "ip_address": battery.address, "username": username, "password": password,
        "auth_token": "", "scan_interval": 30, "sonnenbatterie_debug": False})


def coordinator(hass: HomeAssistant, entry: ConfigEntry):
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


async def refresh(hass: HomeAssistant, entry: ConfigEntry, slow: bool = False) -> None:
    """One update cycle; slow=True also reads the endpoints of the slow cycle."""
    coord = coordinator(hass, entry)
    if slow:
        coord._cycle_count = 0
    await coord.async_refresh()
    await hass.async_block_till_done()


def sensor_id(hass: HomeAssistant, serial: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"sensor.sonnenbatterie_{serial}_{key}")


def control_id(hass: HomeAssistant, domain: str, serial: str, key: str) -> str | None:
    """Entity id of a number, select or button."""
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{DOMAIN}_{serial}_{key}")


def state(hass: HomeAssistant, entity_id: str | None) -> str | None:
    st = hass.states.get(entity_id) if entity_id else None
    return st.state if st else None


def entry_entities(hass: HomeAssistant, entry: ConfigEntry) -> list[er.RegistryEntry]:
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


def stacking(battery: FakeBattery) -> dict:
    """The master's view of the cascade: {"master": {serial: {...}}, "slaves": {...}}."""
    return battery.endpoints["stacking_status"]["data"]["data"]


def point_slaves_to(battery: FakeBattery, addresses: dict[str, str]) -> None:
    """Let a cascade master list its slaves at the given addresses (serial ->
    address). Unlisted slaves get an unreachable address; they're still
    offered as discovered devices, but can't be set up."""
    for serial, slave in stacking(battery)["slaves"].items():
        slave["ip"] = addresses.get(serial, "127.0.0.1:1")
    inverter = battery.endpoints["v1/commissioning_assistant/inverter/stacking/status"]["data"]
    for slave in inverter["slaves"]:
        slave["ip"] = addresses.get(slave["serial"], "127.0.0.1:1")
