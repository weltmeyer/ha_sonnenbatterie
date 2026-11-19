from homeassistant.components.button import ButtonEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LOGGER
from .coordinator import SonnenbatterieConfigEntry, SonnenbatterieCoordinator
from .entities import (
    BUTTON_ENTITIES,
    SonnenbatterieButtonEntityDescription,
    SonnenButtonEntity,
)


async def async_setup_entry(hass: HomeAssistant, config_entry: SonnenbatterieConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    LOGGER.debug(f"BUTTON async_setup_entry - {config_entry}")
    coordinator = config_entry.runtime_data.coordinator

    if coordinator.is_slave:
        # controlled by the cascade's master: read-only
        LOGGER.info(f"cascade slave {coordinator.serial} - no BUTTON entities")
        return

    if coordinator.latestData.get('api_configuration', {}).get('IN_LocalAPIWriteActive', '0') == '1':
        entities = []
        for description in BUTTON_ENTITIES:
            if description.tag.type == Platform.BUTTON:
                entity = SonnenbatterieButton(coordinator, description)
                entities.append(entity)

        async_add_entities(entities)
    else:
        LOGGER.info("JSON-API write access not enabled - disabling BUTTON functions")

class SonnenbatterieButton(SonnenButtonEntity, ButtonEntity):

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieButtonEntityDescription):
        super().__init__(coordinator, description)


    async def async_press(self, **kwargs) -> None:
        tag = self.entity_description.tag
        match tag.key:
            case "button_reset_all":
                await self.coordinator.async_write_setpoint("number_charge", 0, refresh=False)
                await self.coordinator.async_write_setpoint("number_discharge", 0)
            case "button_reset_charge":
                await self.coordinator.async_write_setpoint("number_charge", 0)
            case "button_reset_discharge":
                await self.coordinator.async_write_setpoint("number_discharge", 0)
