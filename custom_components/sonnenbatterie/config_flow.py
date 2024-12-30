# pylint: disable=no-name-in-module
from sonnenbatterie import AsyncSonnenBatterie

# pylint: enable=no-name-in-module
import traceback

from homeassistant import config_entries
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

# pylint: disable=unused-wildcard-import
from .const import *

# pylint: enable=unused-wildcard-import
import voluptuous as vol


class SonnenbatterieFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):

    CONFIG_SCHEMA_USER = vol.Schema(
        {
            vol.Required(CONF_IP_ADDRESS, default="192.168.0.1"): str,
            vol.Required(CONF_USERNAME): vol.In(["User", "Installer"]),
            vol.Required(CONF_PASSWORD, default="sonnenUser3552"): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            vol.Optional(ATTR_SONNEN_DEBUG, default=DEFAULT_SONNEN_DEBUG): cv.boolean,
        }
    )

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:

            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            ipaddress = user_input[CONF_IP_ADDRESS]

            # noinspection PyBroadException
            try:
                my_serial = await self.hass.async_add_executor_job(
                    self._internal_setup, username, password, ipaddress
                )

            except:
                e = traceback.format_exc()
                LOGGER.error(f"Unable to connect to sonnenbatterie: {e}")
                return self._show_form({"base": "connection_error"})

            # async is a fickly beast ...
            sb_serial = await my_serial
            unique_id = f"{DOMAIN}-{sb_serial}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{user_input[CONF_IP_ADDRESS]} ({sb_serial})",
                data={
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_IP_ADDRESS: ipaddress,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    ATTR_SONNEN_DEBUG: user_input[ATTR_SONNEN_DEBUG],
                    CONF_SERIAL_NUMBER: sb_serial,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self.CONFIG_SCHEMA_USER,
            last_step=True,
        )

    async def async_step_reconfigure(self, user_input):
        entry = self._get_reconfigure_entry()
        schema_reconf = vol.Schema(
            {
                vol.Required(
                    CONF_IP_ADDRESS,
                    default = entry.data.get(CONF_IP_ADDRESS) or None
                ): str,
                vol.Required(
                    CONF_USERNAME,
                    default = entry.data.get(CONF_USERNAME) or "User"
                ): vol.In(["User", "Installer"]),
                vol.Required(
                    CONF_PASSWORD,
                    default = entry.data.get(CONF_PASSWORD) or ""
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=entry.data.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL
                ): cv.positive_int,
                vol.Optional(
                    ATTR_SONNEN_DEBUG,
                    default=entry.data.get(ATTR_SONNEN_DEBUG) or DEFAULT_SONNEN_DEBUG)
                : cv.boolean,
            }
        )

        if user_input is not None:
            LOGGER.info(f"Reconfiguring {entry}")
            if entry.data.get(CONF_SERIAL_NUMBER):
                await self.async_set_unique_id(entry.data[CONF_SERIAL_NUMBER])
                self._abort_if_unique_id_configured()
            # noinspection PyBroadException
            try:
                my_serial = await self.hass.async_add_executor_job(
                    self._internal_setup,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_IP_ADDRESS]
                )

            except:
                e = traceback.format_exc()
                LOGGER.error(f"Unable to connect to sonnenbatterie: {e}")
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=schema_reconf,
                    errors={"base": "connection_error"},
                )

            # async is a fickly beast ...
            sb_serial = await my_serial
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=user_input,
                title=f"{user_input[CONF_IP_ADDRESS]} ({sb_serial})",
            )


        return self.async_show_form(
            step_id = "reconfigure",
            data_schema = schema_reconf,
        )


    @staticmethod
    async def _internal_setup(_username, _password, _ipaddress):
        sb_test = AsyncSonnenBatterie(_username, _password, _ipaddress)
        await sb_test.login()
        result = (await sb_test.get_systemdata()).get("DE_Ticket_Number", "Unknown")
        await sb_test.logout()
        return result

    @callback
    def _show_form(self, errors=None):
        """Show the form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=self.CONFIG_SCHEMA_USER,
            errors=errors if errors else {},
        )

"""" rustydust_241226: disabled since all the options have now been moved
to the main data of the Sonnebatterie entry. The code below is kept in place
just in case we want to add in options again.
"""
#     @staticmethod
#     @callback
#     def async_get_options_flow(config_entry):
#         return OptionsFlowHandler(config_entry)
#
#
# class OptionsFlowHandler(config_entries.OptionsFlow):
#     def __init__(self, config_entry):
#         """Initialize options flow."""
#         self._config_entry = config_entry
#         self.options = dict(config_entry.options)
#
#     async def async_step_init(self, user_input=None):
#         """Manage the options."""
#         if user_input is not None:
#             return self.async_create_entry(title="", data=user_input)
#
#         return self.async_show_form(
#             step_id="init",
#             data_schema=vol.Schema(
#                 {
#                     vol.Optional(
#                         CONF_SCAN_INTERVAL,
#                         default=self._config_entry.data.get(
#                             CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
#                         ),
#                     ): cv.positive_int,
#                     vol.Optional(
#                         ATTR_SONNEN_DEBUG,
#                         default=self._config_entry.data.get(
#                             ATTR_SONNEN_DEBUG, DEFAULT_SONNEN_DEBUG
#                         ),
#                     ): bool,
#                 }
#             ),
#         )
#
#     async def _update_options(self):
#         """Update config entry options."""
#         return self.async_create_entry(title="", data=self.options)
