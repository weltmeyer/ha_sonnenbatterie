"""Failed updates after the maintenance grace period: an unreachable battery
is logged at info level (Home Assistant 2026.12+), an error answer as an
error."""

import logging
from time import time

import pytest
from homeassistant.helpers import update_coordinator

from custom_components.sonnenbatterie import coordinator as coordinator_module

from .helpers import coordinator, refresh, sensor_id, setup_battery, state

SERIAL = "100000"
HAS_UNREACHABLE = hasattr(update_coordinator, "UpdateFailedUnreachable")


@pytest.fixture
async def battery_entry(hass, make_battery):
    battery = await make_battery("single")
    entry = await setup_battery(hass, battery)
    return battery, entry


def past_grace(coord) -> None:
    """As if the battery had stopped answering longer ago than the
    maintenance window lasts."""
    coord._last_error = time() - coord.MAINTENANCE_GRACE - 1


def errors(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


async def test_unreachable(hass, battery_entry, caplog):
    battery, entry = battery_entry
    coord = coordinator(hass, entry)
    await battery.stop()
    past_grace(coord)
    with caplog.at_level(logging.INFO):
        await refresh(hass, entry)
    assert type(coord.last_exception) is coordinator_module.UpdateFailedUnreachable
    assert state(hass, sensor_id(hass, SERIAL, "state_battery_inout")) == "unavailable"
    if HAS_UNREACHABLE:
        assert errors(caplog) == []
        assert any("is unavailable" in r.getMessage() for r in caplog.records
                   if r.levelno == logging.INFO)


async def test_error_answer_stays_an_error(hass, battery_entry, caplog):
    """A battery that answers with an error status is reachable: logged as an
    error as before."""
    battery, entry = battery_entry
    coord = coordinator(hass, entry)
    battery.set_error("v1/status", 500)
    past_grace(coord)
    await refresh(hass, entry)
    assert type(coord.last_exception) is update_coordinator.UpdateFailed
    assert state(hass, sensor_id(hass, SERIAL, "state_battery_inout")) == "unavailable"
    assert any("Error fetching" in message for message in errors(caplog))
