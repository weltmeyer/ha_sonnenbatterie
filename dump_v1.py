"""Dumps every known + newly-discovered v1 endpoint from a Sonnenbatterie via
username/password login, so you can see what they actually return.

Usage:
    pip install sonnenbatterie
    python dump_v1.py <ip-address> <username: User|Installer> <password>
"""
import asyncio
import json
import sys

from sonnenbatterie import AsyncSonnenBatterie


async def main(ipaddress: str, username: str, password: str) -> None:
    sb = AsyncSonnenBatterie(username, password, ipaddress)
    await sb.login()

    # Known endpoints with dedicated library methods.
    known_endpoints = {
        "battery_system": sb.get_batterysystem,
        "system_data": sb.get_systemdata,
        "api_configuration": sb.get_api_configuration,
        "commissioning_settings": sb.get_commissioning_settings,
        "battery": sb.get_battery,
        "inverter": sb.get_inverter,
        "powermeter": sb.get_powermeter,
        "status": sb.get_status,
    }

    for name, fetch in known_endpoints.items():
        print(f"\n=== {name} ===")
        try:
            data = await fetch()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(f"FAILED: {e!r}")

    # Newly-discovered endpoints (no dedicated library method yet) - fetched
    # via the library's internal _get(), which reuses the same logged-in
    # session/token.
    raw_paths = {
        "configs/EM_USOC": "configs/EM_USOC",
        "configs/EM_OperatingMode": "configs/EM_OperatingMode",
        "configs/IN_BackupDeviceType": "configs/IN_BackupDeviceType",
        "configs/EM_SURPLUS_FULLCHARGE_ENABLE": "configs/EM_SURPLUS_FULLCHARGE_ENABLE",
        "commissioning_assistant/inverter_setting": "v1/commissioning_assistant/inverter_setting",
        "commissioning_assistant/microgrid": "v1/commissioning_assistant/microgrid",
        "commissioning_assistant/generator": "v1/commissioning_assistant/generator",
        "commissioning_assistant/peak_shaving": "v1/commissioning_assistant/peak_shaving",
        "commissioning_assistant/knx": "v1/commissioning_assistant/knx",
        "operating_modes": "operating_modes",
        "network": "network",
        "webhooks/configurations": "webhooks/configurations",
        "session": "session",
    }

    for name, path in raw_paths.items():
        print(f"\n=== {name} (raw: {path}) ===")
        try:
            data = await sb._get(path)  # noqa: SLF001 - intentional, no public method exists yet
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(f"FAILED: {e!r}")

    await sb.logout()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: python {sys.argv[0]} <ip-address> <username> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))