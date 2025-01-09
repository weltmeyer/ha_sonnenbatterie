from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN,LOGGER

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_entity_cb: AddEntitiesCallback):
    LOGGER.warning("SELECT setting up select entry", config_entry)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]


# class SonnenBatterieSelectEntity(SelectEntity):
