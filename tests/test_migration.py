"""Migration of the control entities' unique ids from <= 2026.3.2 (#174)."""

import logging

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import entry_entities, setup_battery, state

SERIAL = "100000"
CONTROLS = {
    "number": ("number_charge", "number_discharge", "battery_reserve"),
    "select": ("select_operating_mode",),
    "button": ("button_reset_all", "button_reset_charge", "button_reset_discharge"),
}
COUNT = sum(len(keys) for keys in CONTROLS.values())


def controls(hass, entry) -> dict[str, str]:
    """entity id -> unique id of the entry's numbers, select and buttons."""
    return {e.entity_id: e.unique_id for e in entry_entities(hass, entry) if e.domain in CONTROLS}


@pytest.fixture
async def unloaded_entry(hass, make_battery):
    """An entry set up once, then unloaded: the registry can be prepared as
    an older version left it."""
    battery = await make_battery("single", write_access=True)
    entry = await setup_battery(hass, battery)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def add_old_entities(hass, entry) -> dict[str, str]:
    """Registry entries as 2026.3.2 created them: unique id
    "sonnenbatterie.sonnenbatterie_<serial>_<key>", entity id
    "<domain>.sonnenbatterie_<serial>_<key>". Returns entity id -> key."""
    registry = er.async_get(hass)
    old = {}
    for domain, keys in CONTROLS.items():
        for key in keys:
            entity = registry.async_get_or_create(
                domain, DOMAIN, f"{DOMAIN}.{DOMAIN}_{SERIAL}_{key}",
                suggested_object_id=f"{DOMAIN}_{SERIAL}_{key}", config_entry=entry)
            old[entity.entity_id] = key
    return old


async def test_old_entities_taken_over(hass, unloaded_entry):
    """Only old entries: they get the new unique ids and keep their entity
    ids and settings; no duplicates."""
    entry = unloaded_entry
    registry = er.async_get(hass)
    for entity_id in controls(hass, entry):
        registry.async_remove(entity_id)
    old = add_old_entities(hass, entry)
    renamed = next(iter(old))
    registry.async_update_entity(renamed, name="My custom name")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    after = controls(hass, entry)
    assert len(after) == COUNT
    assert after == {entity_id: f"{DOMAIN}_{SERIAL}_{key}" for entity_id, key in old.items()}
    assert all(state(hass, entity_id) not in (None, "unavailable") for entity_id in old)
    assert registry.async_get(renamed).name == "My custom name"

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert controls(hass, entry) == after


async def test_old_and_new_entities_left_alone(hass, unloaded_entry, caplog):
    """Updated to 2026.7.0 or newer before the migration: both stay, the old
    ones are named in one info message."""
    entry = unloaded_entry
    old = add_old_entities(hass, entry)
    before = controls(hass, entry)
    assert len(before) == 2 * COUNT

    with caplog.at_level(logging.INFO, logger="custom_components.sonnenbatterie"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert controls(hass, entry) == before
    messages = [r.getMessage() for r in caplog.records if "can be removed" in r.getMessage()]
    assert len(messages) == 1
    assert all(entity_id in messages[0] for entity_id in old)
