"""Cascades: master, slaves discovered through it, read-only slave entries."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.sonnenbatterie.const import DOMAIN

from .fake_battery import PASSWORD, FakeBattery
from .helpers import (
    coordinator,
    entry_entities,
    point_slaves_to,
    refresh,
    sensor_id,
    setup_battery,
    stacking,
    state,
)

MASTER, SLAVE1, SLAVE2 = "200001", "200002", "200003"
# sensors that make no sense on a slave: the master's cover the whole cascade
MASTER_ONLY = {"consumption_w", "consumption_avg", "production_w", "state_grid_inout", "state_grid_input",
               "state_grid_output", "max_power", "tou_max_power", "cascade_members"}
SLAVE_OWN = {"state_charge_real", "state_charge_user", "state_battery_inout", "battery_system_cycles",
             "state_remaining_capacity_real", "state_total_capacity_real", "state_netfrequency"}


def keys(hass, entry, serial) -> set[tuple[str, str]]:
    """(domain, key) of the entry's entities."""
    out = set()
    for entity in entry_entities(hass, entry):
        uid = entity.unique_id
        for prefix in (f"sensor.sonnenbatterie_{serial}_", f"binary_sensor.sonnenbatterie_{serial}_",
                       f"{DOMAIN}_{serial}_"):
            uid = uid.removeprefix(prefix)
        out.add((entity.domain, uid))
    return out


def discovery_flows(hass) -> dict[str, dict]:
    return {f["context"]["unique_id"].removeprefix(f"{DOMAIN}-"): f
            for f in hass.config_entries.flow.async_progress()
            if f["handler"] == DOMAIN and f["context"]["source"] == "integration_discovery"}


async def confirm(hass, flow, password=PASSWORD):
    return await hass.config_entries.flow.async_configure(flow["flow_id"], {
        "username": "Installer", "password": password, "scan_interval": 30})


async def setup_cascade(hass, make_battery):
    master = await make_battery("cascade_master")
    slaves = {SLAVE1: await make_battery("cascade_slave1", write_access=True),
              SLAVE2: await make_battery("cascade_slave2")}
    point_slaves_to(master, {serial: slave.address for serial, slave in slaves.items()})
    stacking(master)["master"][MASTER]["ip"] = master.address
    entry = await setup_battery(hass, master, username="Installer")
    return master, slaves, entry


async def add_slaves(hass):
    for flow in discovery_flows(hass).values():
        result = await confirm(hass, flow)
        assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return {e.data["serial_number"]: e for e in hass.config_entries.async_entries(DOMAIN)}


async def test_master(hass, make_battery):
    _, _, entry = await setup_cascade(hass, make_battery)
    assert entry.state is ConfigEntryState.LOADED
    assert coordinator(hass, entry).cascading_role == "master"
    k = keys(hass, entry, MASTER)
    assert any(domain == "number" for domain, _ in k)
    assert ("sensor", "consumption_w") in k

    members = hass.states.get(sensor_id(hass, MASTER, "cascade_members"))
    assert members.state == "3"
    assert [(m["role"], m["status"]) for m in members.attributes["members"]] == [
        ("master", "WORKING"), ("slave", "WORKING"), ("slave", "WORKING")]
    assert "127.0.0.1" not in str(members.attributes)     # no IP addresses


async def test_master_cascade_info_fails_at_setup(hass, make_battery):
    """The cascade members sensor exists anyway and fills in later."""
    master = await make_battery("cascade_master")
    point_slaves_to(master, {})
    good = {path: data for path, data in master.endpoints.items() if "stacking" in path}
    for path in good:
        master.set_error(path, 500)
    entry = await setup_battery(hass, master, username="Installer")
    members_id = sensor_id(hass, MASTER, "cascade_members")
    assert state(hass, members_id) == "unknown"
    master.endpoints.update(good)
    await refresh(hass, entry, slow=True)
    assert state(hass, members_id) == "3"


async def test_slaves_discovered(hass, make_battery):
    await setup_cascade(hass, make_battery)
    flows = discovery_flows(hass)
    assert set(flows) == {SLAVE1, SLAVE2}
    assert all(f["step_id"] == "discovery_confirm" for f in flows.values())


async def test_slave_wrong_password(hass, make_battery):
    _, slaves, _ = await setup_cascade(hass, make_battery)
    flow = discovery_flows(hass)[SLAVE1]
    result = await confirm(hass, flow, password="wrong")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "connection_error"}
    assert slaves[SLAVE1].failed_logins == 1
    result = await confirm(hass, flow)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_slaves_read_only(hass, make_battery):
    """Slaves get their own values, but no controls (even with write access
    enabled) and none of the cascade-wide sensors."""
    await setup_cascade(hass, make_battery)
    entries = await add_slaves(hass)
    for serial in (SLAVE1, SLAVE2):
        entry = entries[serial]
        assert entry.state is ConfigEntryState.LOADED
        assert coordinator(hass, entry).is_slave
        k = keys(hass, entry, serial)
        assert not {domain for domain, _ in k} & {"number", "select", "button"}
        assert not {key for _, key in k if key in MASTER_ONLY or key.startswith("meter_")}
        assert SLAVE_OWN <= {key for _, key in k}
    assert state(hass, sensor_id(hass, SLAVE1, "state_charge_user")) == "71"
    # the actions come from the master
    assert hass.services.has_service(DOMAIN, "charge_battery")


async def test_slave_devices_via_master(hass, make_battery):
    _, _, master_entry = await setup_cascade(hass, make_battery)
    entries = await add_slaves(hass)
    await refresh(hass, master_entry, slow=True)
    devices = dr.async_get(hass)
    (master_device,) = dr.async_entries_for_config_entry(devices, master_entry.entry_id)
    for serial in (SLAVE1, SLAVE2):
        (device,) = dr.async_entries_for_config_entry(devices, entries[serial].entry_id)
        assert device.via_device_id == master_device.id
    # configured slaves aren't offered again
    assert not discovery_flows(hass)


async def test_slave_new_ip(hass, make_battery):
    """The master reports a slave at a new address: its entry follows."""
    master, slaves, master_entry = await setup_cascade(hass, make_battery)
    entries = await add_slaves(hass)
    moved = FakeBattery({"endpoints": slaves[SLAVE1].endpoints})
    await moved.start()
    try:
        point_slaves_to(master, {SLAVE1: moved.address, SLAVE2: slaves[SLAVE2].address})
        await refresh(hass, master_entry, slow=True)
        entry = hass.config_entries.async_get_entry(entries[SLAVE1].entry_id)
        assert entry.data["ip_address"] == moved.address
        assert entry.state is ConfigEntryState.LOADED
        assert moved.logins >= 1
    finally:
        await hass.config_entries.async_unload(entries[SLAVE1].entry_id)
        await moved.stop()


async def test_stale_slave_entities_removed(hass, make_battery):
    """Controls and cascade-wide sensors an older version created for a slave
    are removed."""
    await setup_cascade(hass, make_battery)
    entries = await add_slaves(hass)
    entry = entries[SLAVE2]
    registry = er.async_get(hass)
    stale = {"number_charge", "consumption_w", "meter_consumption_0_2_w_total"}
    for domain, uid in (("number", f"{DOMAIN}_{SLAVE2}_number_charge"),
                        ("sensor", f"sensor.sonnenbatterie_{SLAVE2}_consumption_w"),
                        ("sensor", f"sensor.sonnenbatterie_{SLAVE2}_meter_consumption_0_2_w_total")):
        registry.async_get_or_create(domain, DOMAIN, uid, config_entry=entry)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    left = {key for _, key in keys(hass, entry, SLAVE2)}
    assert not left & stale
    assert "state_charge_real" in left


async def test_single_battery(hass, make_battery):
    battery = await make_battery("single")
    entry = await setup_battery(hass, battery)
    k = keys(hass, entry, "100000")
    assert any(domain == "number" for domain, _ in k)
    assert any(key.startswith("meter_") for _, key in k)
    assert ("sensor", "cascade_members") not in k
    assert not discovery_flows(hass)
    assert not any("stacking" in path for _, path in battery.requests)
