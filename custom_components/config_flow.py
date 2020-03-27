from sonnenbatterie import sonnenbatterie
import traceback
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import *
import voluptuous as vol
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
)


class SonnenbatterieFlowHandler(config_entries.ConfigFlow,domain=DOMAIN):
    def __init__(self):
        """Initialize."""
        self.data_schema = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_IP_ADDRESS): str,
        }
    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        #if self._async_current_entries():
        #    return self.async_abort(reason="single_instance_allowed")

        if not user_input:
            return self._show_form()

        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]
        ipaddress=user_input[CONF_IP_ADDRESS]
        
        try:
            sonnenInst=sonnenbatterie(username,password,ipaddress)
            #await self.hass.async_add_executor_job(
            #    Abode, username, password, True, True, True, cache
            #)

        except:
            e = traceback.format_exc()
            LOGGER.error("Unable to connect to sonnenbatterie: %s", e)
            #if ex.errcode == 400:
            #    return self._show_form({"base": "invalid_credentials"})
            return self._show_form({"base": "connection_error"})
        
        return self.async_create_entry(
            title=user_input[CONF_IP_ADDRESS],
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_IP_ADDRESS: ipaddress,
            },
        )

    @callback
    def _show_form(self, errors=None):
        """Show the form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors if errors else {},
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        #if self._async_current_entries():
        #    LOGGER.warning("Only one configuration of abode is allowed.")
        #    return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_user(import_config)