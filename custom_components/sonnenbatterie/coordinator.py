import asyncio
import sys
import traceback
from datetime import timedelta
from time import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME, CONF_PASSWORD, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from sonnenbatterie import AsyncSonnenBatterie

from custom_components.sonnenbatterie import LOGGER, DOMAIN, ATTR_SONNEN_DEBUG
from .const import CONF_AUTH_TOKEN
from .token_client import TokenSonnenBatterie

def _v2_write_class():
    """The v2 (Auth-Token) WRITE-client class, obtained WITHOUT declaring a new
    dependency. It already ships with the `sonnenbatterie` package that provides
    the session client (whose ``sb2`` IS an AsyncSonnenBatterieV2), so reach it
    through that package's own module namespace. Only fall back to the
    (transitively present) sub-package if the library's layout differs. A static
    token from the battery dashboard never expires, so writes configured with one
    don't hit the session-token 401s."""
    mod = sys.modules.get(AsyncSonnenBatterie.__module__)
    cls = getattr(mod, "AsyncSonnenBatterieV2", None)
    if cls is None:
        try:  # pragma: no cover - layout fallback
            from sonnenbatterie2.sonnenbatterie2 import AsyncSonnenBatterieV2 as cls
        except Exception:
            cls = None
    return cls


class SonnenbatterieCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Sonnenbatteries data."""

    # The system/config endpoints change rarely — poll them only every Nth cycle
    # so the battery's small embedded webserver isn't saturated with static reads.
    SLOW_POLL_EVERY = 6

    # The lib defaults to sock_read=6 s / total=10 s. The battery's embedded server
    # regularly needs LONGER than 6 s to answer (busy with EM cycles / cloud sync);
    # every such answer became "Timeout on reading data from socket" although the
    # command was usually applied. Relaxed timeouts turn those into successes.
    TIMEOUT_CONNECT = 6
    TIMEOUT_READ = 30
    TIMEOUT_TOTAL = 40

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, serial: str) -> None:
        # Never log secrets (password / Auth-Token) in clear text.
        _safe = {k: ("***" if k in (CONF_PASSWORD, CONF_AUTH_TOKEN) else v)
                 for k, v in config_entry.data.items()}
        LOGGER.info(f"Initializing SonnenbatterieCoordinator: {_safe}")

        """ private attributes """
        self._batt_reserved_factor = 7.0    # fixed value, reseved percentage of total installed power for internal use
        self._config_entry = config_entry
        self._fullLogsAlreadySent = False
        self._last_error = None
        self._last_login = 0
        self._cycle_count = 0   # schedules the rarely-changing endpoints

        """ public attributes """
        # Serializes ALL device I/O (poll bursts, entity writes, services): the
        # battery's small embedded webserver handles requests one at a time —
        # concurrent requests queue up and run into read timeouts
        # ("Timeout on reading data from socket").
        self.io_lock = asyncio.Lock()
        self.latestData = {}
        self.name = config_entry.title
        self.serial = serial

        username = self._config_entry.data.get(CONF_USERNAME)
        password = self._config_entry.data.get(CONF_PASSWORD)
        token = self._config_entry.data.get(CONF_AUTH_TOKEN)
        ipaddress = self._config_entry.data[CONF_IP_ADDRESS]

        # No username/password configured -> run entirely off the static
        # Auth-Token (dashboard -> Software-Integration). No login, no
        # session-token expiry, so both reads and writes go through it.
        self._token_only = bool(token) and not (username and password)

        self._write_v2 = None
        if self._token_only:
            self.sbconn = TokenSonnenBatterie(ipaddress, token)
            self._relax_timeouts(self.sbconn, self.sbconn.sb2)
            self._write_v2 = self.sbconn.sb2
            LOGGER.info("sonnenbatterie: running token-only (no login)")
        else:
            self.sbconn = AsyncSonnenBatterie(username=username,
                                              password=password,
                                              ipaddress=ipaddress)

            # Optional dedicated write client via a static Auth-Token (no login, no
            # session-token expiry). Used for setpoint writes when configured;
            # otherwise writes go through the v1 session client (sbconn.sb2).
            v2_cls = _v2_write_class() if token else None
            if token and v2_cls is not None:
                try:
                    self._write_v2 = v2_cls(ipaddress, token)
                    self._relax_timeouts(self._write_v2)
                    LOGGER.info("sonnenbatterie: using static Auth-Token for setpoint writes")
                except Exception:  # noqa: BLE001 - fall back to the session client
                    LOGGER.warning("sonnenbatterie: Auth-Token write client init failed", exc_info=True)
                    self._write_v2 = None

        super().__init__(hass,
                         LOGGER,
                         name=DOMAIN,
                         update_interval=timedelta(seconds=config_entry.data.get(CONF_SCAN_INTERVAL, 30)))

    @property
    def device_info(self) -> DeviceInfo:
        # battery_system/system_data are v1-only - unavailable in token-only
        # mode (the static Auth-Token isn't accepted there), so fall back to
        # "unknown" instead of crashing.
        system_data = self.latestData.get("battery_system", {}).get("battery_system", {})
        system_info = self.latestData.get("system_data", {})
        configurations = self.latestData.get("configurations", {})

        software_version = system_data.get('software', {}).get('software_version') or configurations.get('DE_Software', 'unknown')
        firmware_version = system_data.get('software', {}).get('firmware_version', 'unknown')

        # noinspection HttpUrlsUsage
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            configuration_url=f"http://{self._config_entry.data[CONF_IP_ADDRESS]}/",
            manufacturer="Sonnen",
            model=system_info.get("ERP_ArticleName", "unknown"),
            name=f"{DOMAIN} {self.serial}",
            serial_number=f"{self.serial}",
            sw_version=f"{software_version} ({firmware_version})",
            hw_version=f"{system_data.get('system', {}).get('hardware_version', 'unknown')}",
        )

    def populate_battery_info(self):
        """ some manually calculated values """
        # battery_system is v1-only and unavailable in token-only mode - fall
        # back to the (marketing/nominal) values from "configurations", which
        # is always available via v2.
        configurations = self.latestData.get("configurations", {})
        batt_module_capacity = int(
            self.latestData.get("battery_system", {}).get("battery_system", {}).get("system", {}).get("storage_capacity_per_module")
            or configurations.get("CM_MarketingModuleCapacity", 0)
        )
        batt_module_count = int(
            self.latestData.get("battery_system", {}).get("modules")
            or configurations.get("IC_BatteryModules", 0)
        )

        if self.latestData["status"]["BatteryCharging"]:
            battery_current_state = "charging"
        elif self.latestData["status"]["BatteryDischarging"]:
            battery_current_state = "discharging"
        else:
            battery_current_state = "standby"

        self.latestData["battery_info"] = {}
        self.latestData["battery_info"]["current_state"] = battery_current_state
        self.latestData["battery_info"][
            "total_installed_capacity"
        ] = total_installed_capacity = int(batt_module_count * batt_module_capacity)
        self.latestData["battery_info"]["reserved_capacity"] = reserved_capacity = int(
            total_installed_capacity * (self._batt_reserved_factor / 100.0)
        )
        self.latestData["battery_info"]["remaining_capacity"] = remaining_capacity = (
            int(total_installed_capacity * self.latestData["status"]["RSOC"]) / 100.0
        )
        self.latestData["battery_info"]["remaining_capacity_usable"] = max(
            0, int(remaining_capacity - reserved_capacity)
        )

    def _relax_timeouts(self, *clients):
        """Apply relaxed timeouts to the given async client(s). The v1 client
        RE-CREATES its v2 sub-client (sbconn.sb2) on every login, so this must run
        after each login. The lib classes expose no public setters yet."""
        for client in clients:
            if client is None:
                continue
            try:
                client._timeout_total = self.TIMEOUT_TOTAL
                client._timeout_connect = self.TIMEOUT_CONNECT
                client._timeout_read = self.TIMEOUT_READ
                client._timeout = client._set_timeouts()
            except Exception:  # noqa: BLE001 - best effort, keep defaults on failure
                LOGGER.debug("relax_timeouts: client has no timeout attrs", exc_info=True)

    async def _ensure_login(self):
        """Login lazily and after failures only.

        The previous unconditional logout()+login() every 60 s raced writes on
        the SAME connection (their session died mid-request) and added two
        requests per minute. On any update failure the session is considered
        suspect (self._last_login reset to 0) and renewed on the next attempt.
        """
        if self._token_only:
            return  # static token never expires - nothing to log in

        if self._last_login == 0:
            # noinspection PyBroadException
            try:
                await self.sbconn.logout()
            except:
                pass
            await self.sbconn.login()
            self._relax_timeouts(self.sbconn, getattr(self.sbconn, "sb2", None))
            self._last_login = time()

    async def _safe_fetch(self, coro):
        """Await an optional/legacy endpoint fetch without letting it take
        down the rest of the update cycle."""
        try:
            return await coro
        except Exception:  # noqa: BLE001 - best effort, degrade to empty
            LOGGER.debug("sonnenbatterie: optional endpoint fetch failed", exc_info=True)
            return {}

    async def _async_update_data(self):
        """Populate self.latestdata"""
        async with self.io_lock:
            await self._update_locked()

    async def _update_locked(self):
        await self._ensure_login()

        LOGGER.debug(f"COORDINATOR - async_update_data: {self._config_entry.data}")
        slow_due = (not self.latestData
                    or self._cycle_count % self.SLOW_POLL_EVERY == 0)
        self._cycle_count += 1
        try:
            self.latestData["battery"] = await self.sbconn.get_battery()
            self.latestData["inverter"] = await self.sbconn.get_inverter()
            self.latestData["powermeter"] = await self.sbconn.get_powermeter()
            self.latestData["status"] = await self.sbconn.get_status()
            self.latestData["v2_status"] = await self.sbconn.sb2.get_status()

            if slow_due:
                self.latestData["configurations"] = await self.sbconn.sb2.get_configurations()
                # fault flags rarely change; the ~3.3KB payload is the largest of any
                # endpoint we poll, so keep it on the slow cadence with the other
                # diagnostic/config data rather than fetching it every cycle
                self.latestData["latestdata"] = await self.sbconn.sb2.get_latest_data()

                # Legacy v1-only endpoints (no v2 equivalent): fetched independently
                # so one of them failing (e.g. rejected by the firmware in
                # token-only mode) can't prevent the more important data above
                # from being stored.
                self.latestData["battery_system"] = await self._safe_fetch(self.sbconn.get_batterysystem())
                self.latestData["system_data"] = await self._safe_fetch(self.sbconn.get_systemdata())
                self.latestData["api_configuration"] = await self._safe_fetch(self.sbconn.get_api_configuration())
                self.latestData["commissioning_settings"] = await self._safe_fetch(self.sbconn.get_commissioning_settings())

            self._last_error = None

        except Exception as e:
            self._last_login = 0    # session is suspect -> fresh login next try
            LOGGER.debug(traceback.format_exc())
            if self._last_error is not None:
                LOGGER.info(traceback.format_exc() + " ... might be maintenance window")
                elapsed = time() - self._last_error
                if elapsed > 180:
                    LOGGER.error(
                        f"Unable to connecto to Sonnenbatteries at {self._config_entry.data[CONF_IP_ADDRESS]} for {elapsed} seconds. Please check! [{e}]")
            else:
                self._last_error = time()

        # Fixup for older models
        if isinstance(self.latestData.get("powermeter"), dict):
            # noinspection PyBroadException
            try:
                # some new firmware of sonnenbatterie seems to send a dictionary, but we work with a list, so reformat :)
                new_powermeters = []
                for index, dictIndex in enumerate(self.latestData["powermeter"]):
                    new_powermeters.append(self.latestData["powermeter"][dictIndex])
                self.latestData["powermeter"] = new_powermeters
            except:
                e = traceback.format_exc()
                LOGGER.error(e)

        if self._config_entry.data.get(ATTR_SONNEN_DEBUG, False):
            self.send_all_data_to_log()

        self.populate_battery_info()

    async def async_write_setpoint(self, key: str, value) -> None:
        """Write a charge/discharge/reserve setpoint robustly.

        The battery's local API occasionally drops the session (token expiry ->
        401) or answers slowly (socket timeout), and the v1 session client's v2
        sub-client (sbconn.sb2) is None until the first login — the plain write
        path crashed with ``'NoneType' object has no attribute
        'discharge_battery'`` and a single 401 kept failing.

        When a static Auth-Token is configured, the dedicated v2 client is used
        (no login, no session expiry). Otherwise the session client is used with
        an ensure-login and one re-login+retry on failure. A light refresh
        confirms the applied value afterwards."""
        v = int(value)

        async def _do(client) -> None:
            if key == "number_charge":
                await client.charge_battery(v)
            elif key == "number_discharge":
                await client.discharge_battery(v)
            elif key == "battery_reserve":
                await client.set_battery_reserve(v)
            else:
                raise ValueError(f"unknown setpoint key {key!r}")

        async with self.io_lock:
            if self._write_v2 is not None:
                # static token: no login/session — just one retry on a transient
                # socket timeout (the command usually lands even then).
                for attempt in (1, 2):
                    try:
                        await _do(self._write_v2)
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 2:
                            raise
                        LOGGER.debug(f"token setpoint write {key} failed, retry: {e}")
            else:
                for attempt in (1, 2):
                    try:
                        await self._ensure_login()
                        sb2 = getattr(self.sbconn, "sb2", None)
                        if sb2 is None:
                            raise RuntimeError("sonnenbatterie session not established (sb2 is None)")
                        await _do(sb2)
                        break
                    except Exception as e:  # noqa: BLE001
                        self._last_login = 0    # session suspect -> fresh login on retry
                        if attempt == 2:
                            raise
                        LOGGER.debug(f"setpoint write {key} failed, re-login + retry: {e}")
        await self.refresh_after_write()

    async def refresh_after_write(self):
        """Light refresh after a setpoint/mode write: a few targeted reads instead
        of the full poll salvo that async_request_refresh() triggers — writers
        (external controllers) may set values every few seconds, and a full
        request burst per write saturates the battery's webserver."""
        try:
            async with self.io_lock:
                await self._ensure_login()
                self.latestData["status"] = await self.sbconn.get_status()
                self.latestData["v2_status"] = await self.sbconn.sb2.get_status()
                self.latestData["configurations"] = await self.sbconn.sb2.get_configurations()
        except Exception:  # noqa: BLE001
            LOGGER.debug(traceback.format_exc())
            self._last_login = 0
            return
        self.populate_battery_info()
        self.async_set_updated_data(self.latestData)

    async def fetch_sonnenbatterie_on_startup(self):
        """Fetch all config items from Sonnenbatterie."""
        LOGGER.debug(f"Fetching Sonnenbatteries on startup")
        await self._async_update_data()

    def send_all_data_to_log(self):
        """
        Since we're in "debug" mode, send all data to the log, so we don't have to search for the
        variable we're looking for if it's not where we expect it to be
        """
        if not self._fullLogsAlreadySent:
            LOGGER.warning(f"Powermeter data:\n{self.latestData['powermeter']}")
            LOGGER.warning(f"Battery system data:\n{self.latestData['battery_system']}")
            LOGGER.warning(f"Inverted:\n{self.latestData['inverter']}")
            LOGGER.warning(f"System data:\n{self.latestData['system_data']}")
            LOGGER.warning(f"Status:\n{self.latestData['status']}")
            LOGGER.warning(f"Battery:\n{self.latestData['battery']}")
            LOGGER.warning(f"API-Config:\n{self.latestData['api_configuration']}")
            self._fullLogsAlreadySent = True
