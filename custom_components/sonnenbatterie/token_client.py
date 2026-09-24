"""Token-only client for the Sonnenbatterie local API.

Wraps a static Auth-Token (Sonnen app/dashboard -> Settings -> Integrations ->
Software Integration) so the integration can talk to the battery WITHOUT the
username/password session login.

IMPORTANT: the firmware only accepts this static token on the /api/v2/*
endpoints. The legacy, undocumented /api/* endpoints (battery_system,
system_data, the old json_api_configuration/commissioning_assistant paths)
require a session token obtained via username/password login and answer with
401 for the static token, even though they check the same 'Auth-Token'
header. Everything that DOES have a v2 equivalent (battery, inverter,
powermeter, status) is served from there instead; the rest degrades to an
empty/synthetic result rather than failing the whole update.
"""
import aiohttp
from sonnenbatterie2.sonnenbatterie2 import AsyncSonnenBatterieV2

# same defaults as AsyncSonnenBatterie/AsyncSonnenBatterieV2; the coordinator
# relaxes these after construction, same as it does for the other clients
_TIMEOUT_TOTAL = 10
_TIMEOUT_CONNECT = 6
_TIMEOUT_READ = 6


class TokenSonnenBatterie:
    # noinspection HttpUrlsUsage
    def __init__(self, ipaddress: str, token: str):
        self._ipaddress = ipaddress
        self._token = token
        self._baseurl = f"http://{ipaddress}/api/"
        self._session: aiohttp.ClientSession | None = None

        self._timeout_total = _TIMEOUT_TOTAL
        self._timeout_connect = _TIMEOUT_CONNECT
        self._timeout_read = _TIMEOUT_READ
        self._timeout = self._set_timeouts()

        # v2 endpoints (configurations, setpoints, tou schedule, ...) are
        # already token-only in the upstream library - reuse it instead of
        # reimplementing them here.
        self.sb2 = AsyncSonnenBatterieV2(ip_address=ipaddress, api_token=token)

    def _set_timeouts(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(
            total=self._timeout_total,
            connect=self._timeout_connect,
            sock_connect=self._timeout_connect,
            sock_read=self._timeout_read,
        )

    async def _get(self, path: str):
        if self._session is None:
            self._session = aiohttp.ClientSession()

        response = await self._session.get(
            self._baseurl + path,
            headers={"Auth-Token": self._token},
            timeout=self._timeout,
        )
        if response.status != 200:
            response.raise_for_status()
        return await response.json()

    async def _get_v1_optional(self, path: str):
        """Best-effort GET against a legacy v1-only endpoint.

        Returns None instead of raising on ANY failure - not just 401
        (unauthorized). In practice the battery's embedded webserver also
        answers these endpoints with a transient 502 Bad Gateway from time to
        time (unrelated to auth), and callers need the same graceful
        fallback either way.
        """
        try:
            return await self._get(path)
        except Exception:  # noqa: BLE001 - any failure here is "not available"
            return None

    # Endpoints with a v2 equivalent - served from there so they work with
    # just the static token.
    async def get_battery(self):
        return await self.sb2.get_battery_module_data()

    async def get_inverter(self):
        return await self.sb2.get_inverter_data()

    async def get_powermeter(self):
        return await self.sb2.get_powermeter_data()

    async def get_status(self):
        return await self.sb2.get_status()

    # Legacy v1-only endpoints - no v2 equivalent exists. Best effort: some
    # firmware versions may still accept the static token here, otherwise
    # degrade gracefully.
    async def get_batterysystem(self):
        return await self._get_v1_optional("battery_system") or {}

    async def get_systemdata(self):
        return await self._get_v1_optional("system_data") or {}

    async def get_api_configuration(self):
        result = await self._get_v1_optional("json_api/json_api_configuration")
        if result is not None:
            return result
        # Can't ask the battery whether local API read/write access is
        # enabled - a working Auth-Token implies "Software Integration" is
        # switched on, which covers both.
        return {"IN_LocalAPIReadActive": "1", "IN_LocalAPIWriteActive": "1"}

    async def get_commissioning_settings(self):
        return await self._get_v1_optional("v1/commissioning_assistant/special_function") or {}

    async def login(self):
        return  # static token never expires - nothing to log in

    async def logout(self):
        if self._session:
            await self._session.close()
            self._session = None
        await self.sb2.logout()

    def __getattr__(self, name):
        # Convenience methods (set_operating_mode, get_battery_reserve,
        # set_tou_schedule_string, ...) are already implemented token-only
        # on the v2 client - delegate anything not defined above to it.
        return getattr(self.sb2, name)
