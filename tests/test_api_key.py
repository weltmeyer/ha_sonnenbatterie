"""API-key-only mode (fork feature): no user name/password, only the static Auth-Token."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sonnenbatterie.const import DOMAIN

from .fake_battery import TOKEN
from .helpers import control_id, coordinator, refresh, sensor_id, state
from .test_writes import SERIAL, press, set_slider, sliders


async def add_with_api_key(hass, battery):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"login", "api_key"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "api_key"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "ip_address": battery.address, "auth_token": TOKEN,
        "scan_interval": 30, "sonnenbatterie_debug": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return result["result"]


async def test_setup_without_login(hass, make_battery):
    battery = await make_battery("single", write_access=True)
    entry = await add_with_api_key(hass, battery)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["username"] == "" and entry.data["password"] == ""
    assert coordinator(hass, entry)._token_only
    assert battery.logins == 0
    # the v1-only sensors are not created without a login
    assert sensor_id(hass, SERIAL, "tou_max_power") is None
    assert sensor_id(hass, SERIAL, "battery_system_health") is None
    assert state(hass, sensor_id(hass, SERIAL, "state_setpoint")) is not None


async def test_writes_and_read_back(hass, make_battery):
    """Sliders write with the token and show the battery's read-back (latestdata.SetPoint_W)."""
    battery = await make_battery("single", write_access=True)
    entry = await add_with_api_key(hass, battery)
    assert control_id(hass, "number", SERIAL, "number_charge") is not None
    await set_slider(hass, "number_charge", 1000)
    assert battery.posts()[-1] == "v2/setpoint/charge/1000"
    assert sliders(hass) == ("1000", "0")
    await set_slider(hass, "number_discharge", 500)
    assert sliders(hass) == ("0", "500")
    assert state(hass, sensor_id(hass, SERIAL, "state_setpoint")) == "500"
    await press(hass, "button_reset_all")
    assert sliders(hass) == ("0", "0")
    assert battery.logins == 0
    assert entry.state is ConfigEntryState.LOADED


async def test_read_back_follows_a_change_made_elsewhere(hass, make_battery):
    """A setpoint set by someone else (app, controller) shows up after the next poll."""
    battery = await make_battery("single", write_access=True)
    entry = await add_with_api_key(hass, battery)
    battery.endpoints["v2/latestdata"]["data"]["SetPoint_W"] = -800     # negative = charging
    await refresh(hass, entry, slow=True)
    assert sliders(hass) == ("800", "0")
