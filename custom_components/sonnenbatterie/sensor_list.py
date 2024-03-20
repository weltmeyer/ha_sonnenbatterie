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
                    value_fn=lambda coordinator, _index=index, _sensor_meter=sensor_meter: round(
                        coordinator.latestData["powermeter"][_index][_sensor_meter], 2
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
        key="status_sonnenbatterie",
        options=["standby", "charging", "discharging"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData["battery_info"][
            "current_state"
        ],
    ),
    ###
    # consumption
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_current",
        icon="mdi:home-lightning-bolt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Consumption_W"],
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_avg",
        icon="mdi:home-lightning-bolt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"][
            "Consumption_Avg"
        ],
        entity_registry_enabled_default=False,
    ),
    ###
    # production
    SonnenbatterieSensorEntityDescription(
        key="status_production_w",
        icon="mdi:solar-power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            # Prevent having small negative values in production at night
            0
            if (production := coordinator.latestData["status"]["Production_W"]) < 0
            else production
        ),
    ),
    ###
    # grid
    SonnenbatterieSensorEntityDescription(
        key="status_grid_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["GridFeedIn_W"],
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_grid_in",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData["status"]["GridFeedIn_W"]) >= 0
            else abs(power)
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_grid_out",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData["status"]["GridFeedIn_W"]) <= 0
            else power
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_net_frequency",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Hz",
        device_class=SensorDeviceClass.FREQUENCY,
        suggested_display_precision=2,
        value_fn=lambda coordinator: (
            coordinator.latestData.get("inverter", {}).get("status", {}).get("fac")
            or coordinator.latestData.get("battery_system", {})
            .get("grid_information", {})
            .get("fac")
            or coordinator.latestData.get("inverter", {})
            .get("status", {})
            .get("status", {})
            .get("fac")
        ),
    ),
    ###
    # battery
    SonnenbatterieSensorEntityDescription(
        key="status_battery_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Pac_total_W"],
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_in",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData["status"]["Pac_total_W"]) >= 0
            else abs(power)
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_out",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            0
            if (power := coordinator.latestData["status"]["Pac_total_W"]) <= 0
            else power
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_real",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["RSOC"],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_user",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["USOC"],
    ),
    ###
    # system
    SonnenbatterieSensorEntityDescription(
        key="status_system_status",
        device_class=SensorDeviceClass.ENUM,
        # TODO if known, the possible states should be added (e.g. options=["OnGrid", "AnotherState"],).
        #       However, if defined, it will throw an error if the current state is not in the list
        value_fn=lambda coordinator: (
            # for some reason translation throws an error when using uppercase chars (even tough it is working)
            coordinator.latestData["status"]["SystemStatus"].lower()
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_operating_mode",
        options=["1", "2", "6", "10"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData["status"]["OperatingMode"],
    ),
    ###########################
    ### -- advanced sensors ###
    ###
    # grid
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_ipv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ipv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_ipv2",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ipv2"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_ppv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ppv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_ppv2",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("ppv2"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_upv",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        value_fn=lambda coordinator: coordinator.latestData.get("inverter", {})
        .get("status", {})
        .get("upv"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="inverter_status_upv2",
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
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData["battery_info"][
            "total_installed_capacity"
        ],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_installed_capacity_usable",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: (
            coordinator.latestData["battery_info"]["total_installed_capacity"]
            - coordinator.latestData["battery_info"]["reserved_capacity"]
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_remaining_capacity_total",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData["battery_info"][
            "remaining_capacity"
        ],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_remaining_capacity_usable",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData["battery_info"][
            "remaining_capacity_usable"
        ],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_storage_capacity_per_module",
        icon="mdi:battery-charging",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Wh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData["battery_system"][
            "battery_system"
        ]["system"]["storage_capacity_per_module"],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_module_count",
        icon="mdi:battery",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData["battery_system"][
            "modules"
        ],
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="battery_grid_ipv",
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
