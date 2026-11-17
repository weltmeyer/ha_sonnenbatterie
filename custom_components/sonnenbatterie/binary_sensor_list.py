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
    ###
    # setpoint priorities, from /api/v2/latestdata (ic_status.Setpoint Priority)
    SonnenbatterieBinarySensorEntityDescription(
        key="latestdata_full_charge_request",
        icon="mdi:battery-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.latestData.get("latestdata", {})
        .get("ic_status", {})
        .get("Setpoint Priority", {})
        .get("Full Charge Request"),
        entity_registry_enabled_default=False,
    ),
)


def generate_powermeter_binary_sensors(coordinator: SonnenbatterieCoordinator):
    """A problem sensor per power meter, from its 'error' field (0 = OK,
    e.g. -1 when the meter has failed, #168)."""
    descriptions: list[SonnenbatterieBinarySensorEntityDescription] = []
    for index, meter in enumerate(coordinator.latestData.get("powermeter") or []):
        if not isinstance(meter, dict) or meter.get("error") is None:
            continue
        prefix = f"meter_{meter['direction']}_{meter['deviceid']}_{meter['channel']}".lower()
        descriptions.append(
            SonnenbatterieBinarySensorEntityDescription(
                key=f"{prefix}_error",
                name=f"meter {meter['direction']} {meter['channel']} error",
                icon="mdi:meter-electric-outline",
                device_class=BinarySensorDeviceClass.PROBLEM,
                entity_category=EntityCategory.DIAGNOSTIC,
                value_fn=lambda coordinator, _index=index: _meter_error(coordinator, _index),
            )
        )
    return descriptions


def _meter_error(coordinator: SonnenbatterieCoordinator, index: int) -> bool | None:
    try:
        error = coordinator.latestData["powermeter"][index]["error"]
    except (KeyError, IndexError, TypeError):
        return None
    if error is None:
        return None
    return error != 0


def io_pin_description(pin: str, usage: str) -> SonnenbatterieBinarySensorEntityDescription:
    """Entity description for one digital I/O pin from /api/v2/io (e.g. "DO_2")."""

    def _state(coordinator: SonnenbatterieCoordinator) -> bool | None:
        pin_state = (coordinator.latestData.get("io") or {}).get(pin)
        if not isinstance(pin_state, dict) or pin_state.get("status") is None:
            return None
        return bool(pin_state["status"])

    return SonnenbatterieBinarySensorEntityDescription(
        key=f"io_{pin.lower()}",
        # no translation exists for these keys; the name comes from the battery
        name=f"IO {pin} {usage}",
        icon="mdi:electric-switch",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_state,
        entity_registry_enabled_default=False,
    )
