"""Dumps every v2 endpoint from a Sonnenbatterie using just the Auth-Token
(no login) - the same static token used for API-key-only mode.

Read-only by default. Two opt-in tests WRITE to the battery, to document how
the newer site/* endpoints (firmware >= 1.40) behave:

    --test-limits          PUT site/limits with a harmless limit (the inverter's
                           own max power, for 10 s), GET it back right away and
                           again after it should have expired.
    --test-setpoint WATTS  POST the legacy setpoint/discharge/WATTS, then check
                           whether GET site/setpoint and latestdata.SetPoint_W
                           reflect it (right away, +5 s and +35 s), then reset
                           with setpoint/discharge/0. The setpoint is write-only,
                           so the previous value cannot be restored - an
                           external controller has to write again afterwards.

Usage:
    pip install sonnenbatterie
    python dump_v2.py <ip-address> <auth-token> [--test-limits] [--test-setpoint WATTS]
"""
import argparse
import asyncio
import json
from datetime import datetime

import aiohttp
from sonnenbatterie2.sonnenbatterie2 import AsyncSonnenBatterieV2

MAX_TEST_SETPOINT_W = 1000


async def raw_request(session, ip, token, method, path, body=None) -> str:
    """Plain request that always reports the HTTP status and body, also for
    errors (the library helpers raise on anything but 200)."""
    stamp = datetime.now().strftime("%H:%M:%S")
    try:
        async with session.request(
            method,
            f"http://{ip}/api/v2/{path}",
            headers={"Auth-Token": token},
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            status = resp.status
    except Exception as e:  # noqa: BLE001
        return f"[{stamp}] {method} /api/v2/{path} -> FAILED: {e!r}"
    try:
        shown = json.dumps(json.loads(text), indent=2, ensure_ascii=False) if text else "(empty body)"
    except ValueError:
        shown = text
    return f"[{stamp}] {method} /api/v2/{path} -> HTTP {status}\n{shown}"


async def setpoint_in_latestdata(sb2) -> str:
    try:
        data = await sb2.get_latest_data()
        return f"latestdata: SetPoint_W={data.get('SetPoint_W')} Pac_total_W={data.get('Pac_total_W')}"
    except Exception as e:  # noqa: BLE001
        return f"latestdata FAILED: {e!r}"


async def test_limits(session, sb2, ip, token) -> None:
    print("\n=== TEST: PUT site/limits (writes to the battery!) ===")
    try:
        inverter_max = int((await sb2.get_configurations())["IC_InverterMaxPower_w"])
    except Exception as e:  # noqa: BLE001
        print(f"Skipping: could not read IC_InverterMaxPower_w ({e!r})")
        return
    print(f"Using p_bess_inv_max_export_limit={inverter_max} W (= inverter max, no real restriction) for 10 s")
    body = {"p_bess_inv_max_export_limit": inverter_max, "duration": "PT10S"}
    print(await raw_request(session, ip, token, "PUT", "site/limits", body))
    print(await raw_request(session, ip, token, "GET", "site/limits"))
    await asyncio.sleep(12)
    print("--- after the 10 s duration should have expired ---")
    print(await raw_request(session, ip, token, "GET", "site/limits"))


async def test_setpoint(session, sb2, ip, token, watts) -> None:
    print(f"\n=== TEST: legacy POST setpoint/discharge/{watts} (writes to the battery!) ===")
    print("Overwrites the current setpoint; the previous value cannot be restored.")
    print(await raw_request(session, ip, token, "POST", f"setpoint/discharge/{watts}"))
    for label, wait in (
        ("right away", 0),
        ("+5 s", 5),
        ("+35 s (past the default 30 s remote command timer)", 30),
    ):
        await asyncio.sleep(wait)
        print(f"--- {label} ---")
        print(await raw_request(session, ip, token, "GET", "site/setpoint"))
        print(await setpoint_in_latestdata(sb2))
    print("--- reset ---")
    print(await raw_request(session, ip, token, "POST", "setpoint/discharge/0"))


async def main(args) -> None:
    sb2 = AsyncSonnenBatterieV2(ip_address=args.ip, api_token=args.token)

    endpoints = {
        "status": sb2.get_status,
        "battery": sb2.get_battery_module_data,
        "inverter": sb2.get_inverter_data,
        "powermeter": sb2.get_powermeter_data,
        "io": sb2.get_io_data,
        "configurations": sb2.get_configurations,
        "latestdata": sb2.get_latest_data,
    }

    async with aiohttp.ClientSession() as session:
        try:
            for name, fetch in endpoints.items():
                print(f"\n=== {name} ===")
                try:
                    data = await fetch()
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                except Exception as e:  # noqa: BLE001
                    print(f"FAILED: {e!r}")

            # Not in the python library yet - plain requests so that status
            # codes (404 on older firmware, 400 "EM2", ...) are visible.
            for path in ("site/setpoint", "site/limits"):
                print(f"\n=== {path} (firmware >= 1.40) ===")
                print(await raw_request(session, args.ip, args.token, "GET", path))

            if args.test_limits:
                await test_limits(session, sb2, args.ip, args.token)
            if args.test_setpoint is not None:
                await test_setpoint(session, sb2, args.ip, args.token, args.test_setpoint)
        finally:
            await sb2.logout()


def parse_args():
    parser = argparse.ArgumentParser(description="Dump all Sonnenbatterie API v2 endpoints (read-only by default).")
    parser.add_argument("ip", help="IP address of the battery")
    parser.add_argument("token", help="Auth-Token from the dashboard (Software-Integration)")
    parser.add_argument("--test-limits", action="store_true",
                        help="WRITES: harmless PUT site/limits (inverter max, 10 s) and read it back")
    parser.add_argument("--test-setpoint", type=int, metavar="WATTS",
                        help=f"WRITES: legacy discharge setpoint (1-{MAX_TEST_SETPOINT_W} W), "
                             "check if site/setpoint reflects it, then reset to 0")
    args = parser.parse_args()
    if args.test_setpoint is not None and not 0 < args.test_setpoint <= MAX_TEST_SETPOINT_W:
        parser.error(f"--test-setpoint must be between 1 and {MAX_TEST_SETPOINT_W} W")
    return args


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
