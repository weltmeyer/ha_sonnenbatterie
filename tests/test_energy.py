"""Energy sensors (kWh) for the energy dashboard: left Riemann sum of the
reported power, gaps, outages, standby noise, restore."""

import pytest

import custom_components.sonnenbatterie.sensor as sensor_module
from custom_components.sonnenbatterie.const import DOMAIN

from .helpers import (
    coordinator,
    entry_entities,
    point_slaves_to,
    sensor_id,
    setup_battery,
    state,
)

MASTER = "200001"
ENERGY = ("energy_grid_import", "energy_grid_export", "energy_battery_charge", "energy_battery_discharge")


def kwh(watts: float, seconds: float) -> float:
    return watts * seconds / 3_600_000


class Rig:
    """A cascade master with a controllable clock."""

    def __init__(self, hass, battery, entry):
        self.hass, self.battery, self.entry = hass, battery, entry
        self.now = 1000.0
        self.good_status = dict(battery.status)

    def monotonic(self) -> float:
        return self.now

    def set_power(self, pac, grid, charging=None, discharging=None):
        status = self.battery.status
        status["Pac_total_W"], status["GridFeedIn_W"] = pac, grid
        # the battery's own flags, as it sets them for real flows
        status["BatteryCharging"] = pac < 0 if charging is None else charging
        status["BatteryDischarging"] = pac > 0 if discharging is None else discharging

    async def step(self, seconds, pac=None, grid=None):
        if pac is not None:
            self.set_power(pac, grid)
        self.now += seconds
        await coordinator(self.hass, self.entry).async_refresh()
        await self.hass.async_block_till_done()

    def value(self, key) -> float | None:
        try:
            return float(state(self.hass, sensor_id(self.hass, MASTER, key)))
        except (TypeError, ValueError):
            return None

    def values(self) -> dict[str, float | None]:
        return {key: self.value(key) for key in ENERGY}

    def fail(self):
        self.battery.set_error("v1/status", 500)

    def recover(self, pac=-2000, grid=500):
        self.battery.set_data("v1/status", dict(self.good_status))
        self.set_power(pac, grid)

    async def outage(self, fail_at, ok_at):
        """Polls fail at the given times (s after the last fresh one), as the
        coordinator's back-off spaces them, then succeed at ok_at."""
        t = 0
        self.fail()
        for at in fail_at:
            await self.step(at - t)
            t = at
        self.recover()
        await self.step(ok_at - t)


@pytest.fixture
async def rig(hass, make_battery, monkeypatch):
    battery = await make_battery("cascade_master")
    point_slaves_to(battery, {})
    rig = Rig(hass, battery, None)
    monkeypatch.setattr(sensor_module, "time", rig)
    rig.set_power(0, 0)
    rig.entry = await setup_battery(hass, battery, username="Installer")
    rig.good_status = dict(battery.status)
    return rig


async def charging_rig(rig):
    """Charging 2 kW, exporting 0.5 kW, counted for a while."""
    await rig.step(0, -2000, 500)
    await rig.step(30)
    return rig.values()


async def test_entities(hass, rig):
    ids = {key: sensor_id(hass, MASTER, key) for key in ENERGY}
    assert all(ids.values())
    attributes = hass.states.get(ids["energy_grid_import"]).attributes
    assert attributes["device_class"] == "energy"
    assert attributes["state_class"] == "total_increasing"
    assert attributes["unit_of_measurement"] == "kWh"
    assert attributes["friendly_name"].endswith("Grid import energy")
    assert all(value == 0 for value in rig.values().values())


async def test_meter_counters(hass, rig):
    """The meters' own kWh counters: production enabled, exported disabled."""
    meters = {m["direction"]: m for m in rig.battery.endpoints["v2/powermeter"]["data"]}
    entities = entry_entities(hass, rig.entry)
    (production,) = [e for e in entities if e.unique_id.endswith("_kwh_imported") and "production" in e.unique_id]
    st = hass.states.get(production.entity_id)
    assert float(st.state) == pytest.approx(round(meters["production"]["kwh_imported"], 3), abs=1e-3)
    assert st.attributes["device_class"] == "energy"
    assert st.attributes["state_class"] == "total_increasing"
    exported = [e for e in entities if e.unique_id.endswith("_kwh_exported")]
    assert exported
    assert all(e.disabled_by is not None for e in exported)


async def test_left_riemann_sum(hass, rig):
    await rig.step(0, 3000, -1000)                 # discharging 3 kW, importing 1 kW
    assert all(value == 0 for value in rig.values().values())
    await rig.step(60, -2000, 500)                 # the previous power counts for 60 s
    assert rig.value("energy_battery_discharge") == pytest.approx(kwh(3000, 60), abs=1e-4)
    assert rig.value("energy_grid_import") == pytest.approx(kwh(1000, 60), abs=1e-4)
    assert rig.value("energy_battery_charge") == 0
    assert rig.value("energy_grid_export") == 0
    await rig.step(30)
    assert rig.value("energy_battery_charge") == pytest.approx(kwh(2000, 30), abs=1e-4)
    assert rig.value("energy_grid_export") == pytest.approx(kwh(500, 30), abs=1e-4)
    assert rig.value("energy_battery_discharge") == pytest.approx(kwh(3000, 60), abs=1e-4)


async def test_gap_longer_than_max_not_counted(hass, rig):
    before = await charging_rig(rig)
    await rig.step(1000)
    assert rig.values() == before


async def test_short_outage_bridged(hass, rig):
    """A failed update keeps the sensors available; the gap is bridged with
    the last fresh power."""
    before = await charging_rig(rig)
    rig.fail()
    await rig.step(30)
    assert all(state(hass, sensor_id(hass, MASTER, key)) not in ("unavailable", "unknown") for key in ENERGY)
    rig.recover()
    await rig.step(250)
    assert rig.value("energy_battery_charge") == pytest.approx(
        before["energy_battery_charge"] + kwh(2000, 280), abs=1e-4)
    assert rig.value("energy_grid_export") == pytest.approx(before["energy_grid_export"] + kwh(500, 280), abs=1e-4)
    assert rig.value("energy_grid_import") == before["energy_grid_import"]


@pytest.mark.parametrize(("fail_at", "ok_at"), [
    ([30, 60, 120, 240], 480),          # maintenance window, 30 s scan interval, with back-off
    ([10, 20, 40, 80, 160], 320),       # a 158 s restart, 10 s scan interval (#158)
])
async def test_maintenance_window_bridged(hass, rig, fail_at, ok_at):
    before = await charging_rig(rig)
    await rig.outage(fail_at, ok_at)
    assert rig.value("energy_battery_charge") == pytest.approx(
        before["energy_battery_charge"] + kwh(2000, ok_at), abs=1e-4)


async def test_long_outage_not_counted(hass, rig):
    before = await charging_rig(rig)
    await rig.outage([30, 60, 120, 240, 480], 780)
    assert rig.values() == before


async def test_no_updates_not_bridged(hass, rig):
    """400 s without any update (e.g. HA not running) aren't counted; counting
    resumes afterwards."""
    before = await charging_rig(rig)
    await rig.step(400)
    assert rig.values() == before
    await rig.step(30)
    assert rig.value("energy_battery_charge") == pytest.approx(
        before["energy_battery_charge"] + kwh(2000, 30), abs=1e-4)


async def test_standby_noise(hass, rig):
    """A few W without the charging flag aren't counted; more than 50 W are
    (in a cascade the master's flags may not cover its slaves)."""
    await charging_rig(rig)
    rig.set_power(-5, 0, charging=False, discharging=False)
    await rig.step(30)                             # counts the previous 2 kW interval
    before = rig.values()
    for _ in range(20):
        await rig.step(30)
    assert rig.value("energy_battery_charge") == before["energy_battery_charge"]

    rig.set_power(-3000, 0, charging=False, discharging=False)
    await rig.step(30)                             # counts the standby interval: 0
    await rig.step(30)
    assert rig.value("energy_battery_charge") == pytest.approx(
        before["energy_battery_charge"] + kwh(3000, 30), abs=1e-4)


async def test_restored_after_reload(hass, rig):
    before = await charging_rig(rig)
    await hass.config_entries.async_reload(rig.entry.entry_id)
    await hass.async_block_till_done()
    assert rig.values() == before
    await rig.step(30)          # the reload's first update took a fresh sample
    assert rig.value("energy_battery_charge") == pytest.approx(
        before["energy_battery_charge"] + kwh(2000, 30), abs=1e-4)


async def test_slave_has_no_energy_sensors(hass, make_battery):
    """The master's values cover the whole cascade."""
    slave = await make_battery("cascade_slave1")
    entry = await setup_battery(hass, slave, username="Installer")
    entities = entry_entities(hass, entry)
    assert not any(sensor_id(hass, "200002", key) for key in ENERGY)
    assert not [e for e in entities if e.domain == "binary_sensor" and e.unique_id.endswith("_error")]
    assert not [e for e in entities if "kwh_" in e.unique_id]
    assert all(e.platform == DOMAIN for e in entities)
