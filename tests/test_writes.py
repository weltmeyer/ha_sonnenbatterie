"""Writes: sliders, reset buttons and actions, all through the coordinator."""

import json

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import control_id, coordinator, setup_battery, state

SERIAL = "100000"


@pytest.fixture
async def battery_entry(hass, make_battery):
    battery = await make_battery("single", write_access=True)
    entry = await setup_battery(hass, battery, username="Installer")
    return battery, entry


def sliders(hass):
    return (state(hass, control_id(hass, "number", SERIAL, "number_charge")),
            state(hass, control_id(hass, "number", SERIAL, "number_discharge")))


def device_id(hass):
    entity_id = control_id(hass, "number", SERIAL, "battery_reserve")
    return er.async_get(hass).async_get(entity_id).device_id


async def set_slider(hass, key, value):
    await hass.services.async_call("number", "set_value", {
        "entity_id": control_id(hass, "number", SERIAL, key), "value": value}, blocking=True)
    await hass.async_block_till_done()


async def press(hass, key):
    await hass.services.async_call("button", "press", {
        "entity_id": control_id(hass, "button", SERIAL, key)}, blocking=True)
    await hass.async_block_till_done()


async def test_no_controls_without_write_access(hass, make_battery):
    battery = await make_battery("single", write_access=False)
    await setup_battery(hass, battery)
    assert control_id(hass, "number", SERIAL, "number_charge") is None
    assert control_id(hass, "select", SERIAL, "select_operating_mode") is None
    assert not hass.services.has_service(DOMAIN, "charge_battery")


async def test_reserve_slider_shows_configured_reserve(hass, battery_entry):
    """#164: the slider shows EM_USOC, also when it's changed elsewhere."""
    battery, entry = battery_entry
    reserve = control_id(hass, "number", SERIAL, "battery_reserve")
    assert state(hass, reserve) == "5"
    await set_slider(hass, "battery_reserve", 20)
    assert battery.configurations["EM_USOC"] == "20"
    assert state(hass, reserve) == "20"
    battery.configurations["EM_USOC"] = "35"       # e.g. in the battery's dashboard
    await coordinator(hass, entry).refresh_after_write()
    await hass.async_block_till_done()
    assert state(hass, reserve) == "35"


async def test_setpoint_sliders(hass, battery_entry):
    """Charge and discharge share one setpoint: setting one zeroes the other."""
    battery, _ = battery_entry
    await set_slider(hass, "number_charge", 1000)
    assert battery.posts()[-1] == "v2/setpoint/charge/1000"
    assert sliders(hass) == ("1000", "0")
    await set_slider(hass, "number_discharge", 500)
    assert battery.posts()[-1] == "v2/setpoint/discharge/500"
    assert sliders(hass) == ("0", "500")


async def test_reset_buttons(hass, battery_entry):
    battery, _ = battery_entry
    await set_slider(hass, "number_charge", 1000)
    await press(hass, "button_reset_charge")
    assert battery.posts()[-1] == "v2/setpoint/charge/0"
    assert sliders(hass) == ("0", "0")
    await set_slider(hass, "number_discharge", 500)
    n = len(battery.posts())
    await press(hass, "button_reset_all")
    assert battery.posts()[n:] == ["v2/setpoint/charge/0", "v2/setpoint/discharge/0"]
    assert sliders(hass) == ("0", "0")


async def test_write_without_session(hass, battery_entry):
    """After a logout the session client's sb2 is None until the next login:
    the buttons used to crash with "'NoneType' object has no attribute ..."."""
    battery, entry = battery_entry
    sbconn = coordinator(hass, entry).sbconn
    await sbconn.logout()
    assert sbconn.sb2 is None
    n = len(battery.posts())
    await press(hass, "button_reset_all")
    assert battery.posts()[n:] == ["v2/setpoint/charge/0", "v2/setpoint/discharge/0"]


async def test_write_after_expired_session(hass, battery_entry):
    """A 401: one new login and a retry."""
    battery, _ = battery_entry
    logins = battery.logins
    battery.reject_next = 1
    await hass.services.async_call(DOMAIN, "charge_battery", {"device_id": device_id(hass), "power": "700"},
                                   blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert battery.logins == logins + 1
    assert battery.posts()[-1] == "v2/setpoint/charge/700"
    assert sliders(hass) == ("700", "0")


async def test_reserve_actions(hass, battery_entry):
    battery, _ = battery_entry
    battery.configurations["EM_USOC"] = "35"
    response = await hass.services.async_call(DOMAIN, "get_battery_reserve", {"device_id": device_id(hass)},
                                              blocking=True, return_response=True)
    assert response == {"backup_reserve": 35}
    response = await hass.services.async_call(DOMAIN, "set_battery_reserve",
                                              {"device_id": device_id(hass), "value": 25},
                                              blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert response == {"battery_reserve": 25}
    assert state(hass, control_id(hass, "number", SERIAL, "battery_reserve")) == "25"


async def test_actions_on_a_cascade_slave(hass, battery_entry, monkeypatch):
    """Writes are refused for a slave (the master controls the cascade),
    reads work."""
    battery, entry = battery_entry
    monkeypatch.setattr(type(coordinator(hass, entry)), "is_slave", property(lambda self: True))
    n = len(battery.posts())
    with pytest.raises(HomeAssistantError, match="cascade slave"):
        await hass.services.async_call(DOMAIN, "charge_battery", {"device_id": device_id(hass), "power": "100"},
                                       blocking=True)
    assert len(battery.posts()) == n
    response = await hass.services.async_call(DOMAIN, "get_operating_mode_num", {"device_id": device_id(hass)},
                                              blocking=True, return_response=True)
    assert response == {"operating_mode": int(battery.configurations["EM_OperatingMode"])}


async def test_tou_schedule_capped(hass, battery_entry):
    """Values above the battery's ToU limit are capped, and the capped
    schedule is what's sent."""
    battery, entry = battery_entry
    limit = entry.runtime_data.tou_max
    schedule = [{"start": "10:00", "stop": "11:00", "threshold_p_max": limit + 1000}]
    response = await hass.services.async_call(
        DOMAIN, "set_tou_schedule", {"device_id": device_id(hass), "schedule": json.dumps(schedule)},
        blocking=True, return_response=True)
    sent = json.loads(battery.puts[-1]["EM_ToU_Schedule"])
    assert sent == [{"start": "10:00", "stop": "11:00", "threshold_p_max": limit}]
    assert json.loads(response["schedule"]) == sent
