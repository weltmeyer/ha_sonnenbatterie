"""The Sonnenbatterie integration."""
from .const import *
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_IP_ADDRESS): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass, config):
    """Set up a skeleton component."""
    #if DOMAIN not in config:
    #    hass.states.async_set('sonnenbatterie.test', 'Works!')
    #    return True
    
    #hass.states.async_set('sonnenbatterie.test', 'Works!')
    return True

async def async_setup_entry(hass, config_entry):
    """Set up Abode integration from a config entry."""
    username = config_entry.data.get(CONF_USERNAME)
    password = config_entry.data.get(CONF_PASSWORD)
    ipaddress = config_entry.data.get(CONF_IP_ADDRESS)
    #hass.states.async_set('sonnenbatterie.test2', 'Works!'+username+' '+password+' '+ipaddress)
    
    hass.async_add_job(hass.config_entries.async_forward_entry_setup(config_entry, "sensor"))
    config_entry.add_update_listener(update_listener)

    return True

async def update_listener(hass, entry):
    hass.async_add_job(hass.config_entries.async_forward_entry_setup(config_entry, "sensor"))

