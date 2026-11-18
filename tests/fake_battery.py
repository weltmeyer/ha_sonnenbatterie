"""A fake sonnenBatterie: answers the local API like the real battery did,
according to an sb_info report (tests/fixtures), on 127.0.0.1."""

import copy
import hashlib
import json
from pathlib import Path

from aiohttp import web

PASSWORD = "pw-good"
CHALLENGE = "c0ffee"
TOKEN = "tok"
FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """A scrubbed sb_info report from tests/fixtures."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeBattery:
    """Serves GET /api/<path> from the report's endpoints, logs in with
    PASSWORD (challenge/response like the battery), and handles the writes
    the integration makes (operating mode, reserve, setpoints)."""

    def __init__(self, report: dict) -> None:
        self.endpoints = copy.deepcopy(report["endpoints"])
        self.port = None
        self.runner = None
        self.logins = 0
        self.failed_logins = 0
        self.requests: list[tuple[str, str]] = []
        self.puts: list[dict] = []
        # simulated failures
        self.refuse_modes = False   # mode changes answered with 403 (e.g. an active VPP)
        self.reject_next = 0        # next N writes answered with 401 (expired session)
        self.fail_5xx = 0           # next N writes answered with 500

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def status(self) -> dict:
        return self.endpoints["v1/status"]["data"]

    @property
    def configurations(self) -> dict:
        return self.endpoints["v2/configurations"]["data"]

    def set_data(self, path: str, data) -> None:
        self.endpoints[path] = {"status": 200, "data": data}

    def set_error(self, path: str, status: int) -> None:
        self.endpoints[path] = {"status": status, "error": f"{status} error"}

    def set_write_access(self, enabled: bool) -> None:
        self.endpoints["json_api/json_api_configuration"]["data"]["IN_LocalAPIWriteActive"] = (
            "1" if enabled else "0")

    def set_mode(self, mode) -> None:
        self.configurations["EM_OperatingMode"] = str(mode)
        self.status["OperatingMode"] = str(mode)

    def posts(self) -> list[str]:
        return [path for method, path in self.requests if method == "POST"]

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/api/salt/{user}", self._salt)
        app.router.add_get("/api/challenge", self._challenge)
        app.router.add_post("/api/session", self._session)
        app.router.add_route("*", "/api/{path:.*}", self._api)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = self.runner.addresses[0][1]

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _salt(self, request):
        return web.json_response({"error": "not found"}, status=404)

    async def _challenge(self, request):
        return web.json_response(CHALLENGE)

    async def _session(self, request):
        form = await request.post()
        pw = hashlib.sha512(PASSWORD.encode()).hexdigest()
        expected = hashlib.pbkdf2_hmac("sha512", pw.encode(), CHALLENGE.encode(), 7500, 64).hex()
        if form.get("response") != expected:
            self.failed_logins += 1
            return web.json_response({"error": "401 Unauthorized"}, status=401)
        self.logins += 1
        return web.json_response({"authentication_token": TOKEN})

    async def _api(self, request):
        path = request.match_info["path"]
        self.requests.append((request.method, path))
        if request.headers.get("Auth-Token") != TOKEN:
            return web.json_response({"error": "401 Unauthorized"}, status=401)
        if request.method in ("PUT", "POST"):
            if self.fail_5xx > 0:
                self.fail_5xx -= 1
                return web.json_response({"error": "500 Internal Server Error"}, status=500)
            if self.reject_next > 0:
                self.reject_next -= 1
                return web.json_response({"error": "401 Unauthorized"}, status=401)
        if request.method == "PUT" and path == "v2/configurations":
            return await self._put_configurations(request)
        if request.method == "POST":
            return web.json_response({})
        if path.startswith("v2/configurations/"):
            item = path.rsplit("/", 1)[1]
            return web.json_response({item: self.configurations[item]})
        r = self.endpoints.get(path)
        if r is None:
            return web.json_response({"error": "not found"}, status=404)
        if r.get("status") != 200:
            return web.json_response({"error": r.get("error", "error")}, status=r.get("status") or 500)
        return web.json_response(r["data"])

    async def _put_configurations(self, request):
        body = json.loads(await request.text())
        self.puts.append(body)
        if "EM_USOC" in body:
            self.configurations["EM_USOC"] = str(body["EM_USOC"])
            return web.json_response({"EM_USOC": str(body["EM_USOC"])})
        mode = body.get("EM_OperatingMode")
        if mode is not None:
            # writable modes according to sonnen; the battery decides
            if self.refuse_modes or mode not in ("1", "2", "10", "11"):
                return web.json_response({"error": "403 Forbidden"}, status=403)
            self.set_mode(mode)
            return web.json_response({"EM_OperatingMode": mode})
        self.configurations.update({k: str(v) for k, v in body.items()})
        return web.json_response(body)
