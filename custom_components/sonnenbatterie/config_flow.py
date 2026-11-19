import traceback

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from sonnenbatterie import AsyncSonnenBatterie

# pylint: disable=unused-wildcard-import
from .const import *

# masked input for fields prefilled with a stored secret
SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class SonnenbatterieFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):

    CONFIG_SCHEMA_USER = vol.Schema(
        {
            vol.Required(CONF_IP_ADDRESS, default="192.168.0.1"): str,
            vol.Required(CONF_USERNAME): vol.In(["User", "Installer"]),
            vol.Required(CONF_PASSWORD, default="sonnenUser3552"): str,
            # Optional static Auth-Token (dashboard -> Software-Integration): when
            # set, setpoint writes use it (no login, no session-token 401s).
            vol.Optional(CONF_AUTH_TOKEN, default=""): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
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
                sb_serial = await self._internal_setup(username, password, ipaddress)

            except Exception:  # noqa: BLE001 - any failure: show the connection error
                e = traceback.format_exc()
                LOGGER.error(f"Unable to connect to sonnenbatterie: {e}")
                return self._show_form({"base": "connection_error"})

            unique_id = f"{DOMAIN}-{sb_serial}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{user_input[CONF_IP_ADDRESS]} ({sb_serial})",
                data={
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_IP_ADDRESS: ipaddress,
                    CONF_AUTH_TOKEN: user_input.get(CONF_AUTH_TOKEN, ""),
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

    async def async_step_integration_discovery(self, discovery_info):
        """A cascade master found one of its slaves (see the coordinator).
        Known slave: keep its IP up to date (the master's list is the source,
        the IPs come from DHCP). New slave: ask for its credentials."""
        serial = discovery_info[CONF_SERIAL_NUMBER]
        ipaddress = discovery_info[CONF_IP_ADDRESS]
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_SERIAL_NUMBER) != serial:
                continue
            if entry.data.get(CONF_IP_ADDRESS) != ipaddress:
                LOGGER.info(f"cascade slave {serial} moved to a new IP address, updating its entry")
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_IP_ADDRESS: ipaddress},
                    title=f"{ipaddress} ({serial})")
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(f"{DOMAIN}-{serial}")
        self._abort_if_unique_id_configured()   # also when the user ignored it
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"serial": serial}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        """Credentials for a discovered slave, the master's as defaults. One
        login per submit: failed logins make the battery block further ones."""
        serial = self._discovery[CONF_SERIAL_NUMBER]
        ipaddress = self._discovery[CONF_IP_ADDRESS]
        master = self.hass.config_entries.async_get_entry(
            self._discovery.get(CONF_MASTER_ENTRY_ID, ""))
        master_data = master.data if master is not None else {}
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=master_data.get(CONF_USERNAME) or "User"):
                    vol.In(["User", "Installer"]),
                vol.Required(CONF_PASSWORD, default=master_data.get(CONF_PASSWORD) or ""): SECRET,
                vol.Optional(CONF_SCAN_INTERVAL,
                             default=master_data.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL):
                    vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
            }
        )
        placeholders = {"serial": serial, "ip_address": ipaddress}
        errors = {}
        if user_input is not None:
            # noinspection PyBroadException
            try:
                sb_serial = await self._internal_setup(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD], ipaddress)
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"Unable to log in to cascade slave {serial}: {type(e).__name__}: {e}")
                LOGGER.debug(traceback.format_exc())
                errors["base"] = "connection_error"
            else:
                if str(sb_serial) != str(serial):
                    return self.async_abort(reason="wrong_device")
                return self.async_create_entry(
                    title=f"{ipaddress} ({serial})",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_IP_ADDRESS: ipaddress,
                        CONF_AUTH_TOKEN: "",
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        ATTR_SONNEN_DEBUG: DEFAULT_SONNEN_DEBUG,
                        CONF_SERIAL_NUMBER: serial,
                    },
                )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=schema,
            description_placeholders=placeholders,
            errors=errors,
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
                ): SECRET,
                vol.Optional(
                    CONF_AUTH_TOKEN,
                    default = entry.data.get(CONF_AUTH_TOKEN) or ""
                ): SECRET,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=max(MIN_SCAN_INTERVAL,
                                entry.data.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Optional(
                    ATTR_SONNEN_DEBUG,
                    default=entry.data.get(ATTR_SONNEN_DEBUG) or DEFAULT_SONNEN_DEBUG)
                : cv.boolean,
            }
        )

        if user_input is not None:
            LOGGER.debug(f"Reconfiguring {entry}")
            if entry.data.get(CONF_SERIAL_NUMBER):
                await self.async_set_unique_id(entry.data[CONF_SERIAL_NUMBER])
                self._abort_if_unique_id_configured()
            # noinspection PyBroadException
            try:
                sb_serial = await self._internal_setup(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_IP_ADDRESS]
                )

            except Exception:  # noqa: BLE001 - any failure: show the connection error
                e = traceback.format_exc()
                LOGGER.error(f"Unable to connect to sonnenbatterie: {e}")
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=schema_reconf,
                    errors={"base": "connection_error"},
                )

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
        try:
            await sb_test.login()
            return (await sb_test.get_systemdata()).get("DE_Ticket_Number", "Unknown")
        finally:
            # also after a failed login: closes the HTTP session
            await sb_test.logout()

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
