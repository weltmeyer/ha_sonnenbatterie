"""Operating mode: select, sensor and actions."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_get_all_descriptions

from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import control_id, refresh, sensor_id, setup_battery, state

SERIAL = "100000"


@pytest.fixture
async def battery_entry(hass, make_battery):
    battery = await make_battery("single", write_access=True)
    battery.set_mode(2)
    entry = await setup_battery(hass, battery, username="Installer")
    return battery, entry


def select_id(hass):
    return control_id(hass, "select", SERIAL, "select_operating_mode")


def mode_states(hass):
    return state(hass, select_id(hass)), state(hass, sensor_id(hass, SERIAL, "operating_mode"))


def device_id(hass):
    return er.async_get(hass).async_get(select_id(hass)).device_id


async def select(hass, option):
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": select_id(hass), "option": option}, blocking=True)
    await hass.async_block_till_done()


async def test_select_and_sensor(hass, battery_entry):
    assert "optimizing" in hass.states.get(select_id(hass)).attributes["options"]
    assert mode_states(hass) == ("automatic", "2")


async def test_select_optimizing(hass, battery_entry):
    battery, _ = battery_entry
    await select(hass, "optimizing")
    assert battery.puts[-1] == {"EM_OperatingMode": "11"}
    assert mode_states(hass) == ("optimizing", "11")


@pytest.mark.parametrize(("mode", "expected"), [
    ("4", ("unknown", "4")),        # testing: can't be selected
    ("6", ("unknown", "6")),        # module extension: can't be selected
    ("99", ("unknown", "unknown")),  # unknown, e.g. from a newer firmware
])
async def test_modes_the_select_cant_show(hass, battery_entry, mode, expected):
    battery, entry = battery_entry
    battery.set_mode(mode)
    await refresh(hass, entry)
    assert mode_states(hass) == expected


async def test_refused_mode_readable_error(hass, battery_entry):
    battery, _ = battery_entry
    battery.refuse_modes = True
    with pytest.raises(HomeAssistantError, match="refused operating mode 11"):
        await select(hass, "optimizing")
    for service, mode in (("set_operating_mode", "optimizing"), ("set_operating_mode_num", "11")):
        with pytest.raises(HomeAssistantError, match="refused operating mode 11"):
            await hass.services.async_call(DOMAIN, service, {"device_id": device_id(hass), "mode": mode},
                                           blocking=True, return_response=True)


async def test_server_error_passed_on(hass, battery_entry):
    """A server error left after the retry isn't reported as "refused"."""
    battery, _ = battery_entry
    battery.fail_5xx = 2
    with pytest.raises(Exception, match="500") as err:
        await select(hass, "manual")
    assert "refused" not in str(err.value)
    battery.fail_5xx = 1        # once: retried and applied
    await select(hass, "manual")
    assert mode_states(hass)[0] == "manual"


async def test_actions(hass, battery_entry):
    async def call(service, mode):
        return await hass.services.async_call(DOMAIN, service, {"device_id": device_id(hass), "mode": mode},
                                              blocking=True, return_response=True)
    assert await call("set_operating_mode", "optimizing") == {"mode": "optimizing"}
    assert await call("set_operating_mode_num", "10") == {"mode": 10}
    assert await call("set_operating_mode_num", "11") == {"mode": 11}
    response = await hass.services.async_call(DOMAIN, "get_operating_mode", {"device_id": device_id(hass)},
                                              blocking=True, return_response=True)
    assert response == {"operating_mode": "optimizing"}


async def test_action_dialogs_offer_optimizing(hass, battery_entry):
    descriptions = await async_get_all_descriptions(hass)
    fields = descriptions[DOMAIN]
    assert "optimizing" in fields["set_operating_mode"]["fields"]["mode"]["selector"]["select"]["options"]
    assert "11" in fields["set_operating_mode_num"]["fields"]["mode"]["selector"]["select"]["options"]
