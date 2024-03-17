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


SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    # status
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_avg",
        translation_key="status_consumption_avg",
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
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_current",
        translation_key="status_consumption_current",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Consumption_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Consumption_W"]
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_production_w",
        translation_key="status_production_w",
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
    SonnenbatterieSensorEntityDescription(
        key="status_grid_inout",
        translation_key="status_grid_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["GridFeedIn_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["GridFeedIn_W"]
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_inout",
        translation_key="status_battery_inout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Pac_total_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Pac_total_W"]
        ),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_real",
        translation_key="status_battery_percentage_real",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["RSOC"],
        exists_fn=lambda coordinator: bool(coordinator.latestData["status"]["RSOC"]),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_battery_percentage_user",
        translation_key="status_battery_percentage_user",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coordinator: coordinator.latestData["status"]["USOC"],
        exists_fn=lambda coordinator: bool(coordinator.latestData["status"]["USOC"]),
    ),
    SonnenbatterieSensorEntityDescription(
        key="status_system_status",
        translation_key="status_system_status",
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
        translation_key="status_operating_mode",
        options=["1", "2", "6", "10"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.latestData["status"]["OperatingMode"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["OperatingMode"]
        ),
    ),
)
