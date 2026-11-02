from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from custom_components.sonnenbatterie.coordinator import SonnenbatterieCoordinator


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Sonnenbatterie binary sensor entity."""
    _attr_has_entity_name: bool = True
    value_fn: Callable[[SonnenbatterieCoordinator], bool | None]


BINARY_SENSORS: tuple[SonnenbatterieBinarySensorEntityDescription, ...] = (
    ###
    # fault flags, from /api/v2/latestdata (ic_status.DC Shutdown Reason)
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_inverter_over_temperature",
        icon="mdi:thermometer-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("DC Shutdown Reason", {})
        .get("Inverter Over Temperature"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_critical_bms_alarm",
        icon="mdi:alert-octagon-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("DC Shutdown Reason", {})
        .get("Critical BMS Alarm"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_hw_shutdown",
        icon="mdi:power-plug-off-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("DC Shutdown Reason", {})
        .get("HW_Shutdown"),
        entity_registry_enabled_default=False,
    ),
    ###
    # grid connection flags, from /api/v2/latestdata (ic_status.Droop mode status)
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_grid_abnormal",
        icon="mdi:transmission-tower-off",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("Droop mode status", {})
        .get("Grid abnormal"),
        entity_registry_enabled_default=False,
    ),
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_grid_detached",
        icon="mdi:transmission-tower-off",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("Droop mode status", {})
        .get("Grid detached"),
        entity_registry_enabled_default=False,
    ),
)
