"""Digital I/O pins (/api/v2/io) as binary sensors (fork feature)."""

from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import entry_entities, refresh, setup_battery, state


def io_entities(hass, entry) -> dict[str, er.RegistryEntry]:
    return {e.unique_id.rsplit("_io_", 1)[1]: e for e in entry_entities(hass, entry)
            if e.domain == "binary_sensor" and "_io_" in e.unique_id}


async def test_only_pins_with_a_function_are_created(hass, make_battery):
    battery = await make_battery("single")
    pins = battery.endpoints["v2/io"]["data"]
    entry = await setup_battery(hass, battery)
    expected = {pin.lower() for pin, pin_state in pins.items() if pin_state["usage"]}
    assert expected, "the fixture should have pins with a function"
    entities = io_entities(hass, entry)
    assert set(entities) == expected
    # diagnostic noise: all off until the user asks for them
    assert all(e.disabled_by is er.RegistryEntryDisabler.INTEGRATION for e in entities.values())


async def test_pin_state_follows_the_battery(hass, make_battery):
    battery = await make_battery("single")
    pin = next(pin for pin, pin_state in battery.endpoints["v2/io"]["data"].items() if pin_state["usage"])
    pins = battery.endpoints["v2/io"]["data"]
    pins[pin]["status"] = 0
    entry = await setup_battery(hass, battery)
    registry = er.async_get(hass)
    entity = io_entities(hass, entry)[pin.lower()]
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, entity.entity_id) == "off"
    attributes = hass.states.get(entity.entity_id).attributes
    assert attributes["pin"] == pin
    assert attributes["connector"] == pins[pin]["connector"]

    pins[pin]["status"] = 1
    await refresh(hass, entry, slow=True)
    assert state(hass, entity.entity_id) == "on"

    # a failing endpoint keeps the last known state instead of wiping it
    battery.set_error("v2/io", 500)
    await refresh(hass, entry, slow=True)
    assert state(hass, entity.entity_id) == "on"


async def test_no_io_endpoint(hass, make_battery):
    """Firmware without /api/v2/io: no pin entities, nothing breaks."""
    battery = await make_battery("single")
    battery.set_error("v2/io", 404)
    entry = await setup_battery(hass, battery)
    assert io_entities(hass, entry) == {}
    assert DOMAIN in hass.config.components
