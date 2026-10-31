import asyncio
import sys
import traceback
from datetime import timedelta
from time import time

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME, CONF_PASSWORD, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sonnenbatterie import AsyncSonnenBatterie

from custom_components.sonnenbatterie import LOGGER, DOMAIN, ATTR_SONNEN_DEBUG
from .const import CONF_AUTH_TOKEN, DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL

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

    # The battery is unreachable for a few minutes every day (nightly
    # maintenance / restart). Failures within this window keep the last known
    # values; only longer outages mark the entities unavailable.
    MAINTENANCE_GRACE = 180
    # While the battery is failing, poll less often (doubling per failed cycle,
    # capped) instead of hammering its webserver with logins and requests.
    MAX_BACKOFF_INTERVAL = 300

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, serial: str) -> None:
        # Never log secrets (password / Auth-Token) in clear text.
        self.safe_config = {k: ("***" if k in (CONF_PASSWORD, CONF_AUTH_TOKEN) else v)
                             for k, v in config_entry.data.items()}
        LOGGER.info(f"Initializing SonnenbatterieCoordinator: {self.safe_config}")

        """ private attributes """
        self._batt_reserved_factor = 7.0    # fixed value, reseved percentage of total installed power for internal use
        self._config_entry = config_entry
        self._fullLogsAlreadySent = False
        self._last_error = None
        self._failures = 0      # consecutive failed update cycles
        self._last_login = 0
        self._cycle_count = 0   # schedules the rarely-changing endpoints
        self._base_interval = timedelta(seconds=max(
            MIN_SCAN_INTERVAL,
            config_entry.data.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL))

        """ public attributes """
        # Serializes ALL device I/O (poll bursts, entity writes, services): the
        # battery's small embedded webserver handles requests one at a time —
        # concurrent requests queue up and run into read timeouts
        # ("Timeout on reading data from socket").
        self.io_lock = asyncio.Lock()
        self.latestData = {}
        self.name = config_entry.title
        self.serial = serial
        self.sbconn = AsyncSonnenBatterie(username=self._config_entry.data[CONF_USERNAME],
                                          password=self._config_entry.data[CONF_PASSWORD],
                                          ipaddress=self._config_entry.data[CONF_IP_ADDRESS])

        # Optional dedicated write client via a static Auth-Token (no login, no
        # session-token expiry). Used for setpoint writes when configured;
        # otherwise writes go through the v1 session client (sbconn.sb2).
        self._write_v2 = None
        token = self._config_entry.data.get(CONF_AUTH_TOKEN)
        v2_cls = _v2_write_class() if token else None
        if token and v2_cls is not None:
            try:
                self._write_v2 = v2_cls(
                    self._config_entry.data[CONF_IP_ADDRESS], token)
                self._relax_timeouts(self._write_v2)
                LOGGER.info("sonnenbatterie: using static Auth-Token for setpoint writes")
            except Exception:  # noqa: BLE001 - fall back to the session client
                LOGGER.warning("sonnenbatterie: Auth-Token write client init failed", exc_info=True)
                self._write_v2 = None

        super().__init__(hass,
                         LOGGER,
                         name=DOMAIN,
                         update_interval=self._base_interval)

    @property
    def device_info(self) -> DeviceInfo:
        system_data = self.latestData["battery_system"]["battery_system"]
        system_info = self.latestData["system_data"]

        # noinspection HttpUrlsUsage
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            configuration_url=f"http://{self._config_entry.data[CONF_IP_ADDRESS]}/",
            manufacturer="Sonnen",
            model=system_info.get("ERP_ArticleName", "unknown"),
            name=f"{DOMAIN} {self.serial}",
            serial_number=f"{self.serial}",
            sw_version=f"{system_data.get('software', {}).get('software_version', 'unknown')} ({system_data.get('software', {}).get('firmware_version', 'unknown')})",
            hw_version=f"{system_data.get('system', {}).get('hardware_version', 'unknown')}",
        )

    def populate_battery_info(self):
        """ some manually calculated values """
        batt_module_capacity = int(
            self.latestData["battery_system"]["battery_system"].get("system", {}).get("storage_capacity_per_module", 0)
        )
        batt_module_count = int(self.latestData["battery_system"]["modules"])

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
        requests per minute. The session is only renewed after an auth error
        (self._last_login reset to 0) or a failed login — not after plain
        connection errors, which would turn every failed cycle during the
        battery's maintenance window into a full login salvo.

        Some of the lib's login requests run without a timeout (aiohttp
        default: 5 min), so bound the whole login to not block io_lock for long.
        """
        if self._last_login == 0 or getattr(self.sbconn, "sb2", None) is None:
            async with asyncio.timeout(self.TIMEOUT_TOTAL):
                # noinspection PyBroadException
                try:
                    await self.sbconn.logout()
                except:
                    pass
                await self.sbconn.login()
            self._relax_timeouts(self.sbconn, getattr(self.sbconn, "sb2", None))
            self._last_login = time()

    @staticmethod
    def _is_auth_error(e: Exception) -> bool:
        """The session token is no longer valid (e.g. after a battery restart)."""
        return isinstance(e, aiohttp.ClientResponseError) and e.status in (401, 403)

    def _has_data(self) -> bool:
        """Data needed by populate_battery_info() / device_info is present."""
        return "status" in self.latestData and "battery_system" in self.latestData

    def _handle_update_success(self):
        if self._last_error is not None:
            LOGGER.info(f"Sonnenbatterie at {self._config_entry.data[CONF_IP_ADDRESS]} "
                        f"is reachable again after {int(time() - self._last_error)} seconds")
        self._last_error = None
        self._failures = 0
        self.update_interval = self._base_interval

    def _handle_update_error(self, e: Exception):
        """Tolerate the battery's daily maintenance window: keep the last known
        values for up to MAINTENANCE_GRACE seconds, back off polling meanwhile,
        and raise UpdateFailed (entities unavailable, logged once by the
        coordinator) for longer outages or if there's no data to fall back to."""
        LOGGER.debug(traceback.format_exc())
        if self._is_auth_error(e):
            self._last_login = 0    # session token invalid -> fresh login next try

        # not repr(e): for aiohttp errors that includes the request headers,
        # i.e. the Auth-Token
        reason = f"{type(e).__name__}: {e}"
        now = time()
        if self._last_error is None:
            self._last_error = now
            LOGGER.info(f"Sonnenbatterie at {self._config_entry.data[CONF_IP_ADDRESS]} not responding, "
                        f"might be maintenance window: {reason}")

        self._failures += 1
        self.update_interval = min(
            self._base_interval * 2 ** (self._failures - 1),
            max(self._base_interval, timedelta(seconds=self.MAX_BACKOFF_INTERVAL)))

        elapsed = now - self._last_error
        if elapsed > self.MAINTENANCE_GRACE or not self._has_data():
            raise UpdateFailed(
                f"Unable to connect to Sonnenbatterie at {self._config_entry.data[CONF_IP_ADDRESS]} "
                f"for {int(elapsed)} seconds: {reason}") from e

    async def _async_update_data(self):
        """Populate self.latestdata"""
        async with self.io_lock:
            await self._update_locked()

    async def _update_locked(self):
        LOGGER.debug(f"COORDINATOR - async_update_data: {self.safe_config}")
        slow_due = (not self.latestData
                    or self._cycle_count % self.SLOW_POLL_EVERY == 0)
        self._cycle_count += 1
        try:
            await self._ensure_login()
            self.latestData["battery"] = await self.sbconn.get_battery()
            self.latestData["inverter"] = await self.sbconn.get_inverter()
            self.latestData["powermeter"] = await self.sbconn.get_powermeter()
            self.latestData["status"] = await self.sbconn.get_status()
            self.latestData["v2_status"] = await self.sbconn.sb2.get_status()

            if slow_due:
                self.latestData["battery_system"] = await self.sbconn.get_batterysystem()
                self.latestData["system_data"] = await self.sbconn.get_systemdata()
                self.latestData["configurations"] = await self.sbconn.sb2.get_configurations()
                self.latestData["api_configuration"] = await self.sbconn.get_api_configuration()
                # fault flags rarely change; the ~3.3KB payload is the largest of any
                # endpoint we poll, so keep it on the slow cadence with the other
                # diagnostic/config data rather than fetching it every cycle
                self.latestData["latestdata"] = await self.sbconn.sb2.get_latest_data()
                self.latestData["commissioning_settings"] = await self.sbconn.get_commissioning_settings()

        except Exception as e:
            # raises UpdateFailed unless within the maintenance grace period,
            # in which case the last known values are served below
            self._handle_update_error(e)
        else:
            self._handle_update_success()

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
                        if self._is_auth_error(e):
                            self._last_login = 0    # token invalid -> fresh login on retry
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
        except Exception as e:  # noqa: BLE001
            LOGGER.debug(traceback.format_exc())
            if self._is_auth_error(e):
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
