"""Fixtures for the sonnenbatterie tests (pytest-homeassistant-custom-component)."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.sonnenbatterie.const import DOMAIN

from .fake_battery import FakeBattery, load_fixture


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.fixture(autouse=True)
def allow_local_sockets(socket_enabled):
    """The fake batteries listen on 127.0.0.1."""
    return


@pytest.fixture
async def make_battery(hass: HomeAssistant):
    """Start fake batteries from tests/fixtures; unloads the entries and
    stops the batteries after the test."""
    batteries: list[FakeBattery] = []

    async def make(fixture: str = "single", write_access: bool | None = None) -> FakeBattery:
        battery = FakeBattery(load_fixture(fixture))
        if write_access is not None:
            battery.set_write_access(write_access)
        await battery.start()
        batteries.append(battery)
        return battery

    yield make

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    for battery in batteries:
        await battery.stop()
