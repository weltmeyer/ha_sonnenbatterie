"""Config flow: user setup, errors, reconfigure."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import TextSelector

from custom_components.sonnenbatterie.const import DOMAIN

from .fake_battery import PASSWORD
from .helpers import point_slaves_to, setup_battery, user_flow

try:  # HA >= 2026.11 serializes flow forms with probatio
    from probatio import to_field_list
except ImportError:
    from voluptuous_serialize import convert as to_field_list


def masked_fields(schema) -> set[str]:
    """The fields the frontend shows as password fields."""
    fields = to_field_list(schema, custom_serializer=cv.custom_serializer)
    return {f["name"] for f in fields if f.get("selector", {}).get("text", {}).get("type") == "password"}


async def test_user_setup(hass, make_battery):
    battery = await make_battery("single")
    entry = await setup_battery(hass, battery)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == f"{DOMAIN}-100000"
    assert entry.data["serial_number"] == "100000"
    assert entry.title == f"{battery.address} (100000)"


async def test_wrong_password_shows_error(hass, make_battery):
    battery = await make_battery("single")
    result = await user_flow(hass, battery, password="wrong")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "connection_error"}
    # one attempt only: failed logins can get the battery to block logins
    assert battery.failed_logins == 1
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_older_login_without_salt(hass, make_battery):
    """Older firmware has no salt (404 on /api/salt): the login without one."""
    battery = await make_battery("single", salted=False)
    entry = await setup_battery(hass, battery)
    assert entry.state is ConfigEntryState.LOADED
    assert battery.logins >= 1
    result = await user_flow(hass, await make_battery("single", salted=False), password="wrong")
    assert result["errors"] == {"base": "connection_error"}


async def test_login_with_new_challenge(hass, make_battery):
    """Current firmware may answer the first login with a new challenge."""
    battery = await make_battery("single")
    battery.new_challenge_once = True
    entry = await setup_battery(hass, battery)
    assert entry.state is ConfigEntryState.LOADED
    assert not battery.new_challenge_once
    assert battery.failed_logins == 0


async def test_unreachable_battery_shows_error(hass, make_battery):
    battery = await make_battery("single")
    await battery.stop()
    result = await user_flow(hass, battery)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "connection_error"}


async def test_same_battery_twice_aborts(hass, make_battery):
    battery = await make_battery("single")
    await setup_battery(hass, battery)
    result = await user_flow(hass, battery)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass, make_battery):
    battery = await make_battery("single")
    entry = await setup_battery(hass, battery)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})
    assert result["type"] is FlowResultType.FORM
    assert masked_fields(result["data_schema"]) == {"password", "auth_token"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "ip_address": battery.address, "username": "Installer", "password": PASSWORD,
        "auth_token": "", "scan_interval": 60, "sonnenbatterie_debug": False})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["username"] == "Installer"
    assert entry.data["scan_interval"] == 60
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_wrong_password(hass, make_battery):
    battery = await make_battery("single")
    entry = await setup_battery(hass, battery)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "ip_address": battery.address, "username": "User", "password": "wrong",
        "auth_token": "", "scan_interval": 30, "sonnenbatterie_debug": False})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "connection_error"}
    assert entry.data["password"] == PASSWORD


async def test_discovery_form(hass, make_battery):
    """A slave offered by its master: masked password, prefilled from the master."""
    master = await make_battery("cascade_master")
    slave = await make_battery("cascade_slave1")
    point_slaves_to(master, {"200002": slave.address})
    await setup_battery(hass, master, username="Installer")
    flows = {f["context"]["unique_id"]: f for f in hass.config_entries.flow.async_progress()
             if f["handler"] == DOMAIN and f["context"]["source"] == "integration_discovery"}
    assert set(flows) == {f"{DOMAIN}-200002", f"{DOMAIN}-200003"}
    flow = flows[f"{DOMAIN}-200002"]
    assert flow["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(flow["flow_id"])
    schema = result["data_schema"].schema
    password = next((key, selector) for key, selector in schema.items() if str(key) == "password")
    assert isinstance(password[1], TextSelector)
    assert password[1].config["type"] == "password"
    assert password[0].default() == PASSWORD
    username = next(key for key in schema if str(key) == "username")
    assert username.default() == "Installer"
    assert "password" in masked_fields(result["data_schema"])
