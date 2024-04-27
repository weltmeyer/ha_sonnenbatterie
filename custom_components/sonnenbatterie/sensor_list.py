from collections.abc import Callable
from dataclasses import dataclass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.typing import StateType
from custom_components.sonnenbatterie.coordinator import SonnenBatterieCoordinator


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieSensorEntityDescription(SensorEntityDescription):
    """Describes Example sensor entity."""
    legacy_key: str = None
    # exists_fn: Callable[[SonnenBatterieCoordinator], bool] = lambda _: True
    value_fn: Callable[[SonnenBatterieCoordinator], StateType]


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
            sensor_name = f"meter {meter['direction']} {sensor_meter}"
            unit = (sensor_meter[0] + "").upper()
            match unit:
                case "V":
                    device_class = SensorDeviceClass.VOLTAGE
                case "A":
                    device_class = SensorDeviceClass.CURRENT
                case "W":
                    device_class = SensorDeviceClass.POWER
                case _:
                    device_class = None
            powermeter_sensors.append(
                SonnenbatterieSensorEntityDescription(
                    key=sensor_key,
                    name=sensor_name,
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
                        else None
                    ),
                    entity_registry_enabled_default=False,
                )
            )
    return powermeter_sensors


SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    ################################
    ### basic sensors ("status") ###
    ###
    # main sensor
    SonnenbatterieSensorEntityDescription(
        key="state_sonnenbatterie",
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
        legacy_key="production_w",
        icon="mdi:solar-power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            # Prevent having small negative values in production at night
            0
            if (
                production := coordinator.latestData.get("status").get(
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
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("status", {}).get(
            "GridFeedIn_W"
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="state_grid_in",
        legacy_key="state_grid_input",
        state_class=SensorStateClass.MEASUREMENT,
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
        legacy_key="state_grid_output",
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
        options=["1", "2", "6", "10"],
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
        key="battery_installed_capacity_total",
        legacy_key="state_total_capacity_real",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
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
        state_class=SensorStateClass.MEASUREMENT,
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
        state_class=SensorStateClass.MEASUREMENT,
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
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get(
            "battery_system", {}
        ).get("modules"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_ipv",
        legacy_key="battery_system_ipv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_system", {})
        .get("grid_information", {})
        .get("ipv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_ppv",
        legacy_key="battery_system_ppv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_system", {})
        .get("grid_information", {})
        .get("ppv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_upv",
        legacy_key="battery_system_upv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_system", {})
        .get("grid_information", {})
        .get("upv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_tmax",
        legacy_key="tmax",
        icon="mdi:thermometer-alert",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda coordinator: coordinator.latestData.get("battery_system", {})
        .get("grid_information", {})
        .get("tmax"),
        entity_registry_enabled_default=False,
    ),
)
