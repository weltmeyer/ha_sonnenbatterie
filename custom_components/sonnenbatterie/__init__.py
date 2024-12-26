"""The Sonnenbatterie integration."""

import json

from homeassistant.const import (
    Platform
)

from .const import *


# rustydust_241227: this doesn't seem to be needed - kept until we're sure ;)
# async def async_setup(hass, config):
#     """Set up a skeleton component."""
#     hass.data.setdefault(DOMAIN, {})
#     return True


async def async_setup_entry(hass, config_entry):
    LOGGER.debug("setup_entry: " + json.dumps(dict(config_entry.data)))
    await hass.config_entries.async_forward_entry_setups(config_entry, [ Platform.SENSOR ])
    # rustydust_241227: this doesn't seem to be needed
    # config_entry.add_update_listener(update_listener)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
     """Reload config entry."""
     await async_unload_entry(hass, entry)
     await async_setup_entry(hass, entry)


# rustydust_241227: this doesn't seem to be needed
# async def update_listener(hass, entry):
#     LOGGER.warning("Update listener" + json.dumps(dict(entry.options)))
#     # hass.data[DOMAIN][entry.entry_id]["monitor"].update_interval_seconds = (
#     #     entry.options.get(CONF_SCAN_INTERVAL)
#     # )


async def async_unload_entry(hass, entry):
    """Handle removal of an entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, Platform.SENSOR)
