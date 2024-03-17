from collections.abc import Callable
from dataclasses import dataclass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.typing import StateType
from custom_components.sonnenbatterie.coordinator import SonnenBatterieCoordinator


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieSensorEntityDescription(SensorEntityDescription):
    """Describes Example sensor entity."""

    exists_fn: Callable[[SonnenBatterieCoordinator], bool] = lambda _: True
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
                    suggested_display_precision=2,  # FIXME not working
                    value_fn=lambda coordinator, _index=index, _sensor_meter=sensor_meter: round(
                        coordinator.latestData["powermeter"][_index][_sensor_meter], 2
                    ),
                    entity_registry_enabled_default=False,
                )
            )
    return powermeter_sensors


SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    #####################
    ### basic sensors ###
    ###
    # consumption
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_current",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Consumption_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Consumption_W"]
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_avg",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        value_fn=lambda coordinator: coordinator.latestData["status"][
            "Consumption_Avg"
        ],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Consumption_Avg"]
        ),
        entity_registry_enabled_default=False,
    ),
    ###
    # production
    SonnenbatterieSensorEntityDescription(
        key="status_production_w",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: (
            # Prevent having small negative values in production at night
            0
            if (production := coordinator.latestData["status"]["Production_W"]) < 0
            else production
        ),
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Production_W"]
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["GridFeedIn_W"]
        ),
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["GridFeedIn_W"]
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["GridFeedIn_W"]
        ),
        entity_registry_enabled_default=False,
    ),
    ###
    # battery
    SonnenbatterieSensorEntityDescription(
        key="status_battery_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Pac_total_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Pac_total_W"]
        ),
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Pac_total_W"]
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Pac_total_W"]
        ),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_real",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["RSOC"],
        exists_fn=lambda coordinator: bool(coordinator.latestData["status"]["RSOC"]),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_user",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["USOC"],
        exists_fn=lambda coordinator: bool(coordinator.latestData["status"]["USOC"]),
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
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["SystemStatus"]
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_operating_mode",
        options=["1", "2", "6", "10"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData["status"]["OperatingMode"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["OperatingMode"]
        ),
    ),
    ###
    ### -- advanced sensors
)
