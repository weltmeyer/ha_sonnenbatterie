from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.sonnenbatterie import SonnenbatterieSensorEntityDescription, SonnenbatterieCoordinator
from custom_components.sonnenbatterie.const import DOMAIN
from custom_components.sonnenbatterie.select_entities import SonnenbatterieSelectEntityDescription


class SonnenBaseEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieSensorEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSensorEntityDescription):
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        # {DOMAIN} is replaced by the correct platform by HA
        self.entity_id = f"{DOMAIN}.sonnenbatterie_{self.coordinator.serial}_{self.entity_description.key}"

        # set the device info
        self._attr_device_info = self.coordinator.device_info

        # set the translation key
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )


class SonnenSelectEntity(CoordinatorEntity[SonnenbatterieCoordinator], Entity):
    entity_description: SonnenbatterieSelectEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True
    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSelectEntityDescription):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        # {DOMAIN} is replaced by the correct platform by HA
        self.entity_id = f"select.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key.lower()}"

        self._attr_device_info = self.coordinator.device_info
        self._attr_translation_key = (
            tkey
            if (tkey := self.entity_description.translation_key)
            else self.entity_description.key
        )
