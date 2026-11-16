import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.helpers.typing import StateType

from custom_components.sonnenbatterie.const import ROLE_MASTER, ROLE_NONE, ROLE_SLAVE
from custom_components.sonnenbatterie.coordinator import SonnenbatterieCoordinator


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieSensorEntityDescription(SensorEntityDescription):
    """Describes Sonnebatterie sensor entity."""
    _attr_has_entity_name: bool = True
    legacy_key: str = None
    # whether to create the sensor at setup; default (None): if it has a value
    exists_fn: Callable[[SonnenbatterieCoordinator], bool] | None = None
    value_fn: Callable[[SonnenbatterieCoordinator], StateType]
    # False: not created for a cascade's slave, where the value is meaningless
    # (the meters are on the master) or a setting of the whole cascade
    on_slave: bool = True
    attrs_fn: Callable[[SonnenbatterieCoordinator], dict | None] | None = None

def generate_powermeter_sensors(_coordinator):
    powermeter_sensors: list[SonnenbatterieSensorEntityDescription] = []

    generate_sensors_for = {
        "a_l1",
        "a_l2",
        "a_l3",
        "v_l1_l2",
        "v_l1_n",
        "v_l2_l3",
        "v_l2_n",
        "v_l3_l1",
        "v_l3_n",
        "w_l1",
        "w_l2",
        "w_l3",
        "w_total",
    }

    """powermeter values"""
    for index, meter in enumerate(_coordinator.latestData["powermeter"]):
        sensor_prefix_key = (
            f"meter_{meter['direction']}_{meter['deviceid']}_{meter['channel']}".lower()
        )

        for sensor_meter in generate_sensors_for:
            sensor_key = f"{sensor_prefix_key}_{sensor_meter}"
            # sensor_name = f"meter {meter['direction']} {sensor_meter}"
            sensor_name = f"meter {meter['direction']} {meter['channel']} {sensor_meter}"
            unit = (sensor_meter[0] + "").upper()
            match unit:
                case "V":
                    device_class = SensorDeviceClass.VOLTAGE
                    icon = "mdi:current-ac"
                case "A":
                    device_class = SensorDeviceClass.CURRENT
                    icon = "mdi:flash-triangle-outline"
                case "W":
                    device_class = SensorDeviceClass.POWER
                    icon = "mdi:meter-electric-outline"
                case _:
                    device_class = None
                    icon = "None"
            powermeter_sensors.append(
                SonnenbatterieSensorEntityDescription(
                    key=sensor_key,
                    name=sensor_name,
                    icon=icon,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    suggested_display_precision=2,
                    value_fn=lambda coordinator, _index=index, _sensor_meter=sensor_meter: (
                        round(val, 2)
                        if (
                            val := coordinator.latestData.get("powermeter", {})[
                                _index
                            ].get(_sensor_meter)
                        )
                        is not None else None
                    ),
                    entity_registry_enabled_default=False,
                )
            )

        # the meter's own energy counters (kWh, keep counting while HA is
        # down): usable in the energy dashboard as they are. kwh_exported
        # has been 0 on all meters seen so far, so it starts disabled.
        for counter, enabled in (("kwh_imported", True), ("kwh_exported", False)):
            if meter.get(counter) is None:
                continue
            powermeter_sensors.append(
                SonnenbatterieSensorEntityDescription(
                    key=f"{sensor_prefix_key}_{counter}",
                    name=f"meter {meter['direction']} {meter['channel']} {counter}",
                    icon="mdi:meter-electric-outline",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    device_class=SensorDeviceClass.ENERGY,
                    suggested_display_precision=2,
                    value_fn=lambda coordinator, _index=index, _counter=counter: (
                        round(val, 3)
                        if (val := coordinator.latestData.get("powermeter", {})[_index].get(_counter))
                        is not None else None
                    ),
                    entity_registry_enabled_default=enabled,
                )
            )

    return powermeter_sensors


def inverter_value(coordinator, key):
    """PV/grid value: live from /api/v2/inverter if the battery offers it,
    else from battery_system's grid_information (same fields, but only polled
    on the slow cycle and as strings). 'nan' / null -> None (unknown)."""
    v2_inverter = coordinator.latestData.get("v2_inverter") or {}
    if key in v2_inverter:
        value = v2_inverter[key]
    else:
        value = coordinator.latestData.get("battery_system", {}).get("grid_information", {}).get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def inverter_has_key(coordinator, key):
    """Whether the battery reports this PV/grid field at all (value may be
    'nan' / null at the moment), see inverter_value()."""
    return key in (coordinator.latestData.get("v2_inverter") or {}) or key in (
        coordinator.latestData.get("battery_system", {}).get("grid_information", {})
    )


# (key pattern, quantity, unit, device class, icon, display precision)
PV_STRING_QUANTITIES = (
    (re.compile(r"^ipv(\d+)$"), "current", "A", SensorDeviceClass.CURRENT, "mdi:current-dc", 2),
    (re.compile(r"^ppv(\d+)_dc$"), "power", "W", SensorDeviceClass.POWER, "mdi:solar-power", 0),
    (re.compile(r"^upv(\d+)$"), "voltage", "V", SensorDeviceClass.VOLTAGE, "mdi:sine-wave", 1),
)


def generate_pv_string_sensors(_coordinator):
    """Current, DC power and voltage per PV string, for every ipvN, ppvN_dc
    and upvN the battery reports, instead of a fixed number of strings. The
    count reflects the API's slots (4 on all systems seen so far, connected
    or not), so the sensors are disabled by default. Detected at setup: a
    string appearing later shows up after a reload."""
    keys = set(_coordinator.latestData.get("v2_inverter") or {}) | set(
        _coordinator.latestData.get("battery_system", {}).get("grid_information", {})
    )
    pv_string_sensors: list[SonnenbatterieSensorEntityDescription] = []
    for pattern, quantity, unit, device_class, icon, precision in PV_STRING_QUANTITIES:
        for string, source_key in sorted((int(m.group(1)), key) for key in keys if (m := pattern.match(key))):
            pv_string_sensors.append(
                SonnenbatterieSensorEntityDescription(
                    key=f"pv_string_{string}_{quantity}",
                    translation_key=f"pv_string_{quantity}",
                    translation_placeholders={"string": str(string)},
                    icon=icon,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    suggested_display_precision=precision,
                    value_fn=lambda coordinator, _key=source_key: inverter_value(coordinator, _key),
                    entity_registry_enabled_default=False,
                )
            )
    return pv_string_sensors


SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    ################################
    ### basic sensors ("status") ###
    ###
    # main sensor
    SonnenbatterieSensorEntityDescription(
        key="state_sonnenbatterie",
        icon="mdi:battery-charging-medium",
        options=["standby", "charging", "discharging"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_info", {}).get(
            "current_state"
        ),
    ),
    ###
    # consumption
    SonnenbatterieSensorEntityDescription(
        key="state_consumption_current",
        on_slave=False,
        legacy_key="consumption_w",
        icon="mdi:home-lightning-bolt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "Consumption_W"
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_consumption_avg",
        on_slave=False,
        legacy_key="consumption_avg",
        icon="mdi:home-lightning-bolt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "Consumption_Avg"
        ),
        entity_registry_enabled_default=False,
    ),
    ###
    # production
    SonnenbatterieSensorEntityDescription(
        key="state_production",
        on_slave=False,
        legacy_key="production_w",
        icon="mdi:solar-power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            # Prevent having small negative values in production at night
            0
            if (
                production := coordinator.latestData.get("status", {}).get(
                    "Production_W", 0
                )
            )
            < 0
            else production
        ),
    ),
    ###
    # grid
    SonnenbatterieSensorEntityDescription(
        key="state_grid_inout",
        on_slave=False,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "GridFeedIn_W"
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_grid_in",
        on_slave=False,
        legacy_key="state_grid_input",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (
                power := coordinator.latestData.get("status", {}).get("GridFeedIn_W", 0)
            )
            >= 0
            else abs(power)
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_grid_out",
        on_slave=False,
        legacy_key="state_grid_output",
        icon="mdi:transmission-tower-import",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (
                power := coordinator.latestData.get("status", {}).get("GridFeedIn_W", 0)
            )
            <= 0
            else power
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_net_frequency",
        legacy_key="state_netfrequency",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Hz",
        device_class=SensorDeviceClass.FREQUENCY,
        suggested_display_precision=2,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("inverter", {}).get("status", {}).get("fac")
            or coordinator.latestData.get("inverter", {}).get("status", {}).get("status", {}).get("fac")
            or coordinator.latestData.get("battery_system", {}).get("grid_information", {}).get("fac")
        ),
    ),
    ###
    # battery
    SonnenbatterieSensorEntityDescription(
        key="state_battery_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "Pac_total_W"
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_battery_in",
        legacy_key="state_battery_input",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData.get("status", {}).get("Pac_total_W", 0))
            >= 0
            else abs(power)
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_battery_out",
        legacy_key="state_battery_output",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData.get("status", {}).get("Pac_total_W", 0))
            <= 0
            else power
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_battery_percentage_real",
        legacy_key="state_charge_real",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "RSOC"
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_battery_percentage_user",
        legacy_key="state_charge_user",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "USOC"
        ),
    ),
    ###
    # system
    SonnenbatterieSensorEntityDescription(
        key="state_system_status",
        icon="mdi:battery-check-outline",
        legacy_key="systemstatus",
        device_class=SensorDeviceClass.ENUM,
        # TODO if known, the possible states should be added (e.g. options=["OnGrid", "AnotherState"],).
        #       However, if defined, it will throw an error if the current state is not in the list
        value_fn=lambda coordinator: (
            # for some reason translation throws an error when using uppercase chars (even tough it is working)
            val.lower()
            if (val := coordinator.latestData.get("status", {}).get("SystemStatus"))
            else None
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_operating_mode",
        legacy_key="operating_mode",
        icon="mdi:state-machine",
        options=["1", "2", "6", "10", "11"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "OperatingMode"
        ),
    ),
    ###########################
    ### -- advanced sensors ###
    ###
    # grid
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_ipv",
        legacy_key="inverter_ipv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ipv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_ipv2",
        legacy_key="inverter_ipv2",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ipv2"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_ppv",
        legacy_key="inverter_ppv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ppv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_ppv2",
        legacy_key="inverter_ppv2",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ppv2"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_upv",
        legacy_key="inverter_upv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("upv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_state_upv2",
        legacy_key="inverter_upv2",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("upv2"),
        entity_registry_enabled_default=False,
    ),
    ###
    # battery system
    SonnenbatterieSensorEntityDescription(
        key="battery_system_cycles",
        icon="mdi:battery-sync",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("battery", {})
            .get("measurements", {})
            .get("battery_status", {})
            .get("cyclecount")
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_system_health",
        icon="mdi:battery-heart-variant",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("battery", {})
            .get("measurements", {})
            .get("battery_status", {})
            .get("stateofhealth")
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_minimum_cell_temperature",
        icon="mdi:thermometer-low",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("battery", {})
            .get("measurements", {})
            .get("battery_status", {})
            .get("minimumcelltemperature")
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_maximum_cell_temperature",
        icon="mdi:thermometer-high",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("battery", {})
            .get("measurements", {})
            .get("battery_status", {})
            .get("maximumcelltemperature")
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_installed_capacity_total",
        legacy_key="state_total_capacity_real",
        icon="mdi:battery-charging",
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_info").get(
            "total_installed_capacity"
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_installed_capacity_usable",
        legacy_key="state_total_capacity_usable",
        icon="mdi:battery-charging",
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("battery_info", {}).get(
                "total_installed_capacity", 0
            )
            - coordinator.latestData.get("battery_info", {}).get("reserved_capacity", 0)
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_remaining_capacity_total",
        legacy_key="state_remaining_capacity_real",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_info", {}).get(
            "remaining_capacity"
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_remaining_capacity_usable",
        legacy_key="state_remaining_capacity_usable",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_info", {}).get(
            "remaining_capacity_usable"
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_storage_capacity_per_module",
        legacy_key="module_capacity",
        icon="mdi:battery-charging",
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_system", {})
        .get("battery_system", {})
        .get("system", {})
        .get("storage_capacity_per_module"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_module_count",
        legacy_key="module_count",
        icon="mdi:battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        # all modules of a cascade, not only the master's
        value_fn=lambda coordinator: coordinator.latestData.get(
            "battery_info", {}
        ).get("module_count"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="cascading_role",
        icon="mdi:battery-sync-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        # a text value: without ENUM, HA takes the sensor for a numeric one
        # (precision 0 by default) and refuses to add it (#152)
        device_class=SensorDeviceClass.ENUM,
        options=[ROLE_MASTER, ROLE_SLAVE, ROLE_NONE],
        value_fn=lambda coordinator: coordinator.latestData.get(
            "battery_info", {}
        ).get("cascading_role"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        # cascade master: number of units in the cascade, with their serials
        # and status ("WORKING") as attributes
        key="cascade_members",
        icon="mdi:battery-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_slave=False,
        # created on every master, also if reading the members failed at
        # setup (shows unknown until the next successful read)
        exists_fn=lambda coordinator: coordinator.cascading_role == ROLE_MASTER,
        value_fn=lambda coordinator: (
            len(info.members)
            if (info := coordinator.latestData.get("cascade")) and info.members
            else None
        ),
        attrs_fn=lambda coordinator: (
            {"members": [{"serial": m.serial, "role": m.role, "status": m.status}
                         for m in info.members]}
            if (info := coordinator.latestData.get("cascade"))
            else None
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="max_power",
        on_slave=False,
        icon="mdi:flash",
        # static config value: no state_class, long-term statistics are pointless
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        # max. charge/discharge power: the whole cascade's on a cascade master
        value_fn=lambda coordinator: coordinator.latestData.get(
            "battery_info", {}
        ).get("max_power"),
        entity_registry_enabled_default=True,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_ipv",
        legacy_key="battery_system_ipv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        exists_fn=lambda coordinator: inverter_has_key(coordinator, "ipv"),
        value_fn=lambda coordinator: inverter_value(coordinator, "ipv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_ppv",
        legacy_key="battery_system_ppv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        exists_fn=lambda coordinator: inverter_has_key(coordinator, "ppv"),
        value_fn=lambda coordinator: inverter_value(coordinator, "ppv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_upv",
        legacy_key="battery_system_upv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        exists_fn=lambda coordinator: inverter_has_key(coordinator, "upv"),
        value_fn=lambda coordinator: inverter_value(coordinator, "upv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_tmax",
        legacy_key="tmax",
        icon="mdi:thermometer-alert",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        exists_fn=lambda coordinator: inverter_has_key(coordinator, "tmax"),
        value_fn=lambda coordinator: inverter_value(coordinator, "tmax"),
        entity_registry_enabled_default=False,
    ),
    ###########################
    ### -- advanced sensors ###
    ###
    SonnenbatterieSensorEntityDescription(
        key="read_api",
        icon="mdi:alpha-r-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("api_configuration", {})
        .get('IN_LocalAPIReadActive', '0') == '1',
        entity_registry_enabled_default=True,
    ),
    SonnenbatterieSensorEntityDescription(
        key="write_api",
        icon="mdi:alpha-w-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn= lambda coordinator: coordinator.latestData.get("api_configuration", {})
        .get('IN_LocalAPIWriteActive', '0') == '1',
        entity_registry_enabled_default = True,
    ),
    SonnenbatterieSensorEntityDescription(
        key="tou_max_power",
        on_slave=False,
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        # numeric string, e.g. '46000'; None (not 'unknown') when missing, as
        # the POWER device class requires a numeric state
        value_fn=lambda coordinator: coordinator.latestData.get("commissioning_settings", {})
                                     .get('data', {}).get('attributes',{}).get('tou_max_power_limit'),
        # always created, as before (shows unknown if the battery doesn't report it)
        exists_fn=lambda _: True,
        entity_registry_enabled_default=True,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_care",
        icon="mdi:wrench-clock",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: (coordinator.latestData.get("v2_status", {})
        .get("dischargeNotAllowed", False) == True),
        entity_registry_enabled_default=True,
    ),
    SonnenbatterieSensorEntityDescription(
        key="backup_buffer",
        icon="mdi:battery-20",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="%",
        value_fn=lambda coordinator: int(coordinator.latestData.get("v2_status", {}).get("BackupBuffer", "0")),
        entity_registry_enabled_default=True,
    ),
)


def _positive(coordinator, field: str, sign: int) -> float | None:
    """sign * the status power field if positive, else 0; None if missing."""
    power = coordinator.latestData.get("status", {}).get(field)
    if power is None:
        return None
    return max(sign * float(power), 0.0)


# Energy (kWh) integrated from the power the battery reports, for the energy
# dashboard: the battery has no counters for these. value_fn returns the
# power in W (>= 0) that SonnenbatterieEnergySensor sums up over time. Not on
# a cascade's slave: on the master these values cover the whole cascade
# (meters and Pac_total_W), so a slave's battery energy would be counted twice.
ENERGY_SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    SonnenbatterieSensorEntityDescription(
        key="energy_grid_import",
        on_slave=False,
        icon="mdi:transmission-tower-export",
        # GridFeedIn_W < 0: drawing from the grid
        value_fn=lambda coordinator: _positive(coordinator, "GridFeedIn_W", -1),
    ),
    SonnenbatterieSensorEntityDescription(
        key="energy_grid_export",
        on_slave=False,
        icon="mdi:transmission-tower-import",
        value_fn=lambda coordinator: _positive(coordinator, "GridFeedIn_W", 1),
    ),
    SonnenbatterieSensorEntityDescription(
        key="energy_battery_charge",
        on_slave=False,
        icon="mdi:battery-arrow-up",
        # Pac_total_W < 0: charging
        value_fn=lambda coordinator: _positive(coordinator, "Pac_total_W", -1),
    ),
    SonnenbatterieSensorEntityDescription(
        key="energy_battery_discharge",
        on_slave=False,
        icon="mdi:battery-arrow-down",
        value_fn=lambda coordinator: _positive(coordinator, "Pac_total_W", 1),
    ),
)
