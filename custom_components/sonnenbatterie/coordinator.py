import asyncio
import sys
import traceback
from datetime import timedelta
from time import time

import aiohttp
from homeassistant.config_entries import ConfigEntry, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME, CONF_PASSWORD, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, discovery_flow
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sonnenbatterie import AsyncSonnenBatterie

from custom_components.sonnenbatterie import LOGGER, DOMAIN, ATTR_SONNEN_DEBUG
from .const import (
    CASCADE_ROLES,
    CONF_AUTH_TOKEN,
    CONF_MASTER_ENTRY_ID,
    CONF_SERIAL_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    ROLE_MASTER,
    ROLE_NONE,
    ROLE_SLAVE,
)
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

    # After a setpoint write the inverter needs a moment (observed: applied
    # somewhere within 5 s) before latestdata.SetPoint_W shows the new value.
    SETTLE_DELAY = 6.0

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
        self._discovered = {}   # cascade master: slave serial -> IP a discovery was started for
        self._v2_inverter_supported = True
        self._base_interval = timedelta(seconds=max(
            MIN_SCAN_INTERVAL,
            config_entry.data.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL))
        self._write_seq = 0     # counts setpoint writes, see after_write()
        self._settling = False
        self._settle_task = None

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
                         update_interval=self._base_interval)

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

    @property
    def cascading_role(self) -> str:
        """master, slave or none (also for firmware without the field)."""
        raw = (self.latestData.get("system_data", {}).get("CN_CascadingRole")
               or self.latestData.get("configurations", {}).get("CN_CascadingRole")
               or ROLE_NONE)
        return CASCADE_ROLES.get(str(raw).lower(), ROLE_NONE)

    @property
    def is_slave(self) -> bool:
        """A cascade's slave: only reports its own unit (no meters) and is
        controlled by the master, so its entry is read-only."""
        return self.cascading_role == ROLE_SLAVE

    def populate_battery_info(self):
        """ some manually calculated values """
        # battery_system is v1-only and empty in token-only mode - the last
        # alternative in each chain below is the (marketing/nominal) value from
        # "configurations", which is always available via v2.
        configurations = self.latestData.get("configurations", {})
        battery_system = self.latestData.get("battery_system", {})
        system = battery_system.get("battery_system", {}).get("system", {})
        batt_module_capacity = int(
            system.get("storage_capacity_per_module")
            or configurations.get("CM_MarketingModuleCapacity")
            or 0
        )

        # In a cascade (several batteries acting as one system) the master's
        # battery_system also describes the whole cascade: stack_modules (all
        # modules) and stack_capacity (summed inverter power, W), while
        # modules / inverter_capacity only cover the master itself. Both stack
        # values are 0 on a single battery.
        batt_module_count = (
            int(battery_system.get("stack_modules") or 0)
            or int(battery_system.get("modules") or 0)
            or int(configurations.get("IC_BatteryModules") or 0)
        )
        max_power = (
            int(battery_system.get("stack_capacity") or 0)
            or int(system.get("inverter_capacity") or 0)
            or int(configurations.get("IC_InverterMaxPower_w") or 0)
        )

        if self.latestData["status"]["BatteryCharging"]:
            battery_current_state = "charging"
        elif self.latestData["status"]["BatteryDischarging"]:
            battery_current_state = "discharging"
        else:
            battery_current_state = "standby"

        self.latestData["battery_info"] = {}
        self.latestData["battery_info"]["current_state"] = battery_current_state
        self.latestData["battery_info"]["cascading_role"] = self.cascading_role
        self.latestData["battery_info"]["module_count"] = batt_module_count
        self.latestData["battery_info"]["max_power"] = max_power
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
        if self._token_only:
            return  # static token never expires - nothing to log in

        if self._last_login == 0 or getattr(self.sbconn, "sb2", None) is None:
            async with asyncio.timeout(self.TIMEOUT_TOTAL):
                # not a bare except: that would also swallow the cancellation
                # asyncio.timeout() uses, and login() would run unbounded
                try:
                    await self.sbconn.logout()
                except Exception:  # noqa: BLE001
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

    @staticmethod
    def _is_auth_error(e: Exception) -> bool:
        """The session token is no longer valid (e.g. after a battery restart)."""
        return isinstance(e, aiohttp.ClientResponseError) and e.status in (401, 403)

    @property
    def has_fresh_data(self) -> bool:
        """The last update actually read the battery. False after a failed
        update, also while the last known values are kept during the
        maintenance window (see _handle_update_error)."""
        return self.last_update_success and self._last_error is None

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

        # Cap the exponent, not just the result: during long outages
        # base * 2**n would overflow timedelta (failure #43 at 30 s). 2**8
        # times the minimum scan interval already exceeds MAX_BACKOFF_INTERVAL.
        self._failures += 1
        self.update_interval = min(
            self._base_interval * 2 ** min(self._failures - 1, 8),
            max(self._base_interval, timedelta(seconds=self.MAX_BACKOFF_INTERVAL)))

        elapsed = now - self._last_error
        if elapsed > self.MAINTENANCE_GRACE or not self._has_data():
            raise UpdateFailed(
                f"Unable to connect to Sonnenbatterie at {self._config_entry.data[CONF_IP_ADDRESS]} "
                f"for {int(elapsed)} seconds: {reason}") from e

    async def _get_v2_inverter(self) -> dict:
        """Live PV/grid values from /api/v2/inverter: the same fields as
        battery_system's grid_information (which is only polled every
        SLOW_POLL_EVERY cycles), as numbers, in a ~3x cheaper request.

        Not every system/firmware may offer it: if the battery says the
        endpoint doesn't exist or isn't permitted, stop asking and let the
        sensors fall back to grid_information. A 403 counts as not permitted:
        /api/v2/status just succeeded with the same token, so it isn't an
        expired session (which would mean a re-login and failed update every
        cycle). Other errors (timeouts, 5xx, 401) are handled like any other
        failed request, so the maintenance window logic applies."""
        try:
            data = await self.sbconn.sb2.get_inverter_data()
        except aiohttp.ClientResponseError as e:
            if e.status not in (400, 403, 404, 405, 501):
                raise
            data = None
        if isinstance(data, dict):
            return data
        LOGGER.info("Sonnenbatterie: /api/v2/inverter not available, "
                    "PV values are taken from battery_system instead")
        self._v2_inverter_supported = False
        return {}

    async def _async_update_data(self):
        """Populate self.latestdata"""
        async with self.io_lock:
            await self._update_locked()
        self._handle_cascade()

    async def _update_cascade(self):
        """Cascade master: read the members (serials, status, IPs) the
        battery's dashboard shows."""
        try:
            self.latestData["cascade"] = await self.sbconn.get_cascade_info()
        except Exception as e:  # optional data, keep the rest of the update
            if self._is_auth_error(e):
                raise
            LOGGER.debug(f"cascade info not available: {type(e).__name__}: {e}")

    @callback
    def _handle_cascade(self) -> None:
        """Cascade master: offer each slave as a discovered device (or update
        its IP, see the config flow), and show configured slaves as connected
        via the master's device."""
        info = self.latestData.get("cascade")
        if info is None or self.cascading_role != ROLE_MASTER:
            return
        slaves = {m.serial: m.raw.get("ip") for m in info.members
                  if m.role == ROLE_SLAVE and m.serial}
        for serial, ip in slaves.items():
            if not ip or self._discovered.get(serial) == ip:
                continue
            self._discovered[serial] = ip
            discovery_flow.async_create_flow(
                self.hass, DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_IP_ADDRESS: ip, CONF_SERIAL_NUMBER: serial,
                      CONF_MASTER_ENTRY_ID: self._config_entry.entry_id})
        self._link_slave_devices(set(slaves))

    @callback
    def _link_slave_devices(self, serials: set) -> None:
        dev_reg = dr.async_get(self.hass)
        master = dev_reg.async_get_device(identifiers={(DOMAIN, self._config_entry.entry_id)})
        if master is None:      # entities (and so the device) not set up yet
            return
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_SERIAL_NUMBER) not in serials:
                continue
            device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
            if device is not None and device.via_device_id != master.id:
                dev_reg.async_update_device(device.id, via_device_id=master.id)

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
            if self._token_only:
                # get_inverter() above already is /api/v2/inverter in this mode
                self.latestData["v2_inverter"] = self.latestData["inverter"]
            elif self._v2_inverter_supported:
                self.latestData["v2_inverter"] = await self._get_v2_inverter()

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
                # commissioning_settings is v1-only and only read by tou_max_power
                # (which is never created in token-only mode) and the TOU limit
                # default in __init__ - skip the request there, it just loads the
                # battery's webserver for data nothing uses.
                if not self._token_only:
                    self.latestData["commissioning_settings"] = await self._safe_fetch(self.sbconn.get_commissioning_settings())

                # cascade members come from a v1 (login-only) endpoint
                if self.cascading_role == ROLE_MASTER and not self._token_only:
                    await self._update_cascade()

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
        await self.after_write()

    @property
    def setpoint_settling(self) -> bool:
        """True from a setpoint write until the read-back has had time to
        catch up - entities show the value that was just written meanwhile."""
        return self._settling

    async def after_write(self) -> None:
        """Refresh right after a setpoint write, and once more when the
        inverter has had time to apply it (latestdata.SetPoint_W lags the
        write by up to a few seconds, so the first read can still return the
        old value). The second refresh runs in the background and is shared by
        writes that arrive in quick succession (external controllers write
        every few seconds), so they don't pile up extra requests."""
        self._write_seq += 1
        self._settling = True
        await self.refresh_after_write()
        if self._settle_task is None or self._settle_task.done():
            self._settle_task = self.hass.async_create_task(self._refresh_after_settle())

    async def _refresh_after_settle(self) -> None:
        try:
            while True:
                seen = self._write_seq
                await asyncio.sleep(self.SETTLE_DELAY)
                if self._write_seq == seen:
                    # last write of a burst: entities switch to the read-back
                    # value in the update this refresh publishes
                    self._settling = False
                await self.refresh_after_write()
                if self._write_seq == seen:
                    return
        finally:
            self._settling = False

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
                # SetPoint_W is the read-back of the charge/discharge setpoint
                self.latestData["latestdata"] = await self.sbconn.sb2.get_latest_data()
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

    async def aclose(self):
        """Close every open aiohttp session (main client + write client, if
        separate). Called on config entry unload/reload - without this the
        underlying ClientSession is only closed by garbage collection, which
        aiohttp warns about as an "Unclosed client session"."""
        if self._settle_task is not None and not self._settle_task.done():
            self._settle_task.cancel()
        try:
            await self.sbconn.logout()
        except Exception:  # noqa: BLE001 - best effort, we're tearing down anyway
            LOGGER.debug("sonnenbatterie: error closing main session", exc_info=True)

        # In login mode with a separate static-token write client, sbconn.sb2
        # is a DIFFERENT AsyncSonnenBatterieV2 instance and needs its own
        # close. In token-only mode self._write_v2 IS sbconn.sb2, already
        # closed above.
        if self._write_v2 is not None and self._write_v2 is not getattr(self.sbconn, "sb2", None):
            try:
                await self._write_v2.logout()
            except Exception:  # noqa: BLE001
                LOGGER.debug("sonnenbatterie: error closing write session", exc_info=True)

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
