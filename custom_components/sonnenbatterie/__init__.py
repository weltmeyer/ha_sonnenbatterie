"""The Sonnenbatterie integration."""

from .const import *
import json

# from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
    CONF_SCAN_INTERVAL,
)


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    """Set up a skeleton component."""
    # if DOMAIN not in config:
    #    hass.states.async_set('sonnenbatterie.test', 'Works!')
    #    return True

    # hass.states.async_set('sonnenbatterie.test', 'Works!')
    return True


async def async_setup_entry(hass, config_entry):
    LOGGER.info("setup_entry: " + json.dumps(dict(config_entry.data)))

    await hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "sensor")
    )
    config_entry.add_update_listener(update_listener)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def update_listener(hass, entry):
    LOGGER.info("Update listener" + json.dumps(dict(entry.options)))
    hass.data[DOMAIN][entry.entry_id]["monitor"].update_interval_seconds = (
        entry.options.get(CONF_SCAN_INTERVAL)
    )


async def async_unload_entry(hass, entry):
    """Handle removal of an entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
