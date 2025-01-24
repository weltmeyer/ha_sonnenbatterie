from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.number import NumberEntityDescription, NumberDeviceClass, NumberMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.const import Platform, EntityCategory
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.sonnenbatterie import SonnenbatterieSensorEntityDescription, SonnenbatterieCoordinator
from custom_components.sonnenbatterie.const import DOMAIN


class SelectEntry(NamedTuple):
    # the key to use for the select entity
    key: str = None
    # the type of value
    type: Platform = None
    # the section where the value is found in the coordinator
    section: str = None
    # the property name of the setting
    property: str = None
    # whether the value is writable or not
    writable: bool = None


class Tag(SelectEntry, Enum):
    def __hash__(self) -> int:
        return hash(self.key)
    def __str__(self) -> str:
        return self.key

    OPERATING_MODE = SelectEntry(
        key="select_operating_mode",
        type=Platform.SELECT,
        section="configurations",
        property="EM_OperatingMode",
        writable=True,
    )

    CHARGE_POWER = SelectEntry(
        key="number_charge",
        type=Platform.NUMBER,
        section="status",
        property="Pac_total_W",
        writable=True,
    )

    DISCHARGE_POWER = SelectEntry(
        key="number_discharge",
        type=Platform.NUMBER,
        section="status",
        property="Pac_total_W",
        writable=True,
    )

    BATTERY_RESERVE = SelectEntry(
        key="battery_reserve",
        type=Platform.NUMBER,
        section="status",
        property="USOC",
        writable=True,
    )

    BTN_RESET_CHARGE = SelectEntry(
        key="button_reset_charge",
        type=Platform.BUTTON,
    )

    BTN_RESET_DISCHARGE = SelectEntry(
        key="button_reset_discharge",
        type=Platform.BUTTON,
    )

    BTN_RESET_ALL = SelectEntry(
        key="button_reset_all",
        type=Platform.BUTTON,
    )


@dataclass(frozen=True,kw_only=True)
class SonnenbatterieSelectEntityDescription(SelectEntityDescription):
    tag: Tag = None


class SonnenBaseEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieSensorEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSensorEntityDescription):
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        # {DOMAIN} is replaced by the correct platform by HA
        self.entity_id = f"{DOMAIN}.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key}"

        # set the device info
        self._attr_device_info = self.coordinator.device_info

        # set the translation key
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )

    @property
    def unique_id(self) -> str:
        return self.entity_id

class SonnenSelectEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieSelectEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSelectEntityDescription):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        # {DOMAIN} is replaced by the correct platform by HA
        self.entity_id = f"{DOMAIN}.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key}"

        self._attr_device_info = self.coordinator.device_info
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )

    @property
    def unique_id(self) -> str:
        return self.entity_id


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieNumberEntityDescription(NumberEntityDescription):
    tag: Tag = None
    native_min_value = 0
    native_step = 1


class SonnenNumberEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieNumberEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieNumberEntityDescription):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = description

        self.entity_id = f"{DOMAIN}.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key}"
        self._attr_device_info = self.coordinator.device_info
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )
        self._number_option_unit_of_measurement="W"

    @property
    def unique_id(self) -> str:
        return self.entity_id


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieButtonEntityDescription(ButtonEntityDescription):
    tag: Tag = None
    _attr_device_class = None

class SonnenButtonEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieButtonEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieButtonEntityDescription):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = description

        self.entity_id = f"{DOMAIN}.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key}"
        self._attr_device_info = self.coordinator.device_info
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )

    @property
    def unique_id(self) -> str:
        return self.entity_id


SELECT_ENTITIES = [
    SonnenbatterieSelectEntityDescription(
        key=Tag.OPERATING_MODE.key,
        icon="mdi:solar-power",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.OPERATING_MODE,
        options=["manual", "automatic", "timeofuse"],
    ),
]

NUMBER_ENTITIES = [
    SonnenbatterieNumberEntityDescription(
        key=Tag.CHARGE_POWER.key,
        icon="mdi:battery-plus-outline",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.CHARGE_POWER,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        native_step=100,
    ),
    SonnenbatterieNumberEntityDescription(
        key=Tag.DISCHARGE_POWER.key,
        icon="mdi:battery-minus-outline",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.DISCHARGE_POWER,
        device_class=NumberDeviceClass.POWER,
        mode=NumberMode.SLIDER,
        native_step=100,
    ),
    SonnenbatterieNumberEntityDescription(
        key=Tag.BATTERY_RESERVE.key,
        icon="mdi:battery-unknown",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.BATTERY_RESERVE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        native_step=1,
    )
]

BUTTON_ENTITIES = [
    SonnenbatterieButtonEntityDescription(
        key=Tag.BTN_RESET_ALL.key,
        icon="mdi:numeric-0-box-multiple-outline",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.BTN_RESET_ALL,
        device_class=None,
    ),
    SonnenbatterieButtonEntityDescription(
        key=Tag.BTN_RESET_CHARGE.key,
        icon="mdi:numeric-0-box-outline",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.BTN_RESET_CHARGE,
        device_class=None,
    ),
    SonnenbatterieButtonEntityDescription(
        key=Tag.BTN_RESET_DISCHARGE.key,
        icon="mdi:numeric-0-box-outline",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.BTN_RESET_DISCHARGE,
        device_class=None,
    )
]
