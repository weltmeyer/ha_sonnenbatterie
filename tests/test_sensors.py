"""Sensors: meter errors (#168), battery care (#132), live PV values (#171),
and every entity enabled at once."""

from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity as ha_entity
from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie import sensor_list
from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import (
    coordinator,
    entry_entities,
    point_slaves_to,
    refresh,
    sensor_id,
    setup_battery,
    state,
)

MASTER = "200001"


def meters(battery, endpoint) -> list[dict]:
    data = battery.endpoints[endpoint]["data"]
    return data if isinstance(data, list) else list(data.values())


async def enable(hass, entry, entity_ids) -> None:
    registry = er.async_get(hass)
    for entity_id in entity_ids:
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def master(hass, make_battery):
    battery = await make_battery("cascade_master")
    point_slaves_to(battery, {})
    entry = await setup_battery(hass, battery, username="Installer")
    return battery, entry


async def test_meter_error(hass, master):
    """A failed meter reports 0 for everything with error -1 (#168): its error
    sensor turns on, its values and counters are unknown instead of 0."""
    battery, entry = master
    errors = [e.entity_id for e in entry_entities(hass, entry)
              if e.domain == "binary_sensor" and e.unique_id.endswith("_error")]
    assert len(errors) == len(meters(battery, "powermeter"))
    assert all(state(hass, e) == "off" for e in errors)
    registry = er.async_get(hass)
    assert all(hass.states.get(e).attributes["device_class"] == "problem" for e in errors)
    assert all(registry.async_get(e).entity_category == "diagnostic" for e in errors)

    meter = meters(battery, "powermeter")[-1]
    prefix = f"sensor.sonnenbatterie_{MASTER}_meter_{meter['direction']}_{meter['deviceid']}_{meter['channel']}"
    counter = registry.async_get_entity_id("sensor", DOMAIN, f"{prefix}_kwh_imported".lower())
    power = registry.async_get_entity_id("sensor", DOMAIN, f"{prefix}_w_total".lower())
    await enable(hass, entry, (counter, power))
    lifetime = round(meter["kwh_imported"], 3)
    assert float(state(hass, counter)) == pytest.approx(lifetime, abs=1e-3)
    power_normal = state(hass, power)
    assert power_normal not in ("unknown", "unavailable")

    saved = {ep: dict(meters(battery, ep)[-1]) for ep in ("powermeter", "v2/powermeter")}
    for ep in ("powermeter", "v2/powermeter"):
        failed = meters(battery, ep)[-1]
        failed.update({k: 0 for k, v in failed.items()
                       if isinstance(v, (int, float)) and k not in ("channel", "deviceid")})
        failed["error"] = -1
    await refresh(hass, entry)
    assert state(hass, power) == "unknown"
    assert state(hass, counter) == "unknown"
    assert sorted(state(hass, e) for e in errors) == ["off"] * (len(errors) - 1) + ["on"]

    # error cleared, but the counter still 0: no drop to 0 (a reset for HA)
    for ep in ("powermeter", "v2/powermeter"):
        meters(battery, ep)[-1]["error"] = 0
    await refresh(hass, entry)
    assert state(hass, counter) == "unknown"

    for ep in ("powermeter", "v2/powermeter"):
        meters(battery, ep)[-1].update(saved[ep])
    await refresh(hass, entry)
    assert state(hass, power) == power_normal
    assert float(state(hass, counter)) == pytest.approx(lifetime, abs=1e-3)
    assert all(state(hass, e) == "off" for e in errors)


async def test_battery_care(hass, master):
    """#132: only latestdata's ic_status shows the battery care mode."""
    battery, entry = master
    care = sensor_id(hass, MASTER, "battery_care")
    assert state(hass, care) == "False"
    ic_status = battery.endpoints["v2/latestdata"]["data"]["ic_status"]
    normal = {"led": ic_status["Eclipse Led"]["Eclipse Status"], "reason": dict(ic_status["Full Charge Reason"])}

    ic_status["Eclipse Led"]["Eclipse Status"] = "0x14 - INFO_BATTERY_CARE"
    ic_status["Full Charge Reason"].update({"Maintenance": True, "None": False})
    await refresh(hass, entry, slow=True)       # latestdata is read on the slow cycle
    st = hass.states.get(care)
    assert st.state == "True"
    assert st.attributes["full_charge_reason"] == ["Maintenance"]
    assert st.attributes["led_status"] == "0x14 - INFO_BATTERY_CARE"

    ic_status["Eclipse Led"]["Eclipse Status"] = normal["led"]
    ic_status["Full Charge Reason"] = normal["reason"]
    await refresh(hass, entry, slow=True)
    assert state(hass, care) == "False"


async def test_discharge_not_allowed_is_not_battery_care(hass, master):
    battery, entry = master
    battery.endpoints["v2/status"]["data"]["dischargeNotAllowed"] = True
    await refresh(hass, entry, slow=True)
    assert state(hass, sensor_id(hass, MASTER, "battery_care")) == "False"


@pytest.mark.parametrize("latest", [
    {"latestdata": None},
    {"latestdata": {"ic_status": None}},
    {"latestdata": {"ic_status": {"Full Charge Reason": None, "Eclipse Led": None}}},
    {"latestdata": {"ic_status": {"Eclipse Led": {"Eclipse Status": None}}}},
])
def test_battery_care_with_nulls(latest):
    """Null values on some firmware must not keep the sensor platform from loading."""
    fake = SimpleNamespace(latestData=latest)
    assert sensor_list._battery_care(fake) is False
    sensor_list._battery_care_attrs(fake)


@pytest.mark.parametrize("fixture", ["single", "cascade_master"])
async def test_inverter_endpoint_refused(hass, make_battery, fixture):
    """#171: some systems answer 401 on /api/v2/inverter. The integration
    loads, doesn't log in again on every update, and takes the PV values
    from battery_system instead."""
    battery = await make_battery(fixture)
    if fixture == "cascade_master":
        point_slaves_to(battery, {})
    battery.set_error("v2/inverter", 401)
    entry = await setup_battery(hass, battery, username="User")
    assert entry.state is ConfigEntryState.LOADED
    coord = coordinator(hass, entry)
    logins = battery.logins
    for _ in range(coord.SLOW_POLL_EVERY + 1):
        await refresh(hass, entry)
    assert coord.last_update_success
    assert battery.logins == logins
    assert not coord._v2_inverter_supported
    assert ("GET", "v2/inverter") not in battery.requests[-30:]
    production = [e for e in entry_entities(hass, entry) if e.domain == "sensor" and e.disabled_by is None
                  and ("ppv" in e.unique_id or "production" in e.unique_id)]
    assert production
    assert all(state(hass, e.entity_id) not in ("unknown", "unavailable") for e in production)


@pytest.mark.parametrize("fixture", ["single", "cascade_master", "cascade_slave1"])
async def test_all_entities_enabled(hass, make_battery, fixture, monkeypatch, caplog):
    """Every entity, also the ones disabled by default: HA adds all of them
    without errors (e.g. no text sensor taken for a numeric one)."""
    monkeypatch.setattr(ha_entity.Entity, "entity_registry_enabled_default", property(lambda self: True))
    battery = await make_battery(fixture, write_access=True)
    if fixture == "cascade_master":
        point_slaves_to(battery, {})
    entry = await setup_battery(hass, battery, username="User")
    await refresh(hass, entry, slow=True)
    entities = entry_entities(hass, entry)
    assert entities
    assert all(hass.states.get(e.entity_id) is not None for e in entities)
    errors = [r for r in caplog.records if r.levelname in ("ERROR", "CRITICAL")]
    assert not errors, [r.getMessage() for r in errors]
