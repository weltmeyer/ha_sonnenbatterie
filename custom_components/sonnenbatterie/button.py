from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonnenbatterieCoordinator
from .const import CONF_COORDINATOR, DOMAIN, LOGGER
from .entities import SonnenButtonEntity, SonnenbatterieButtonEntityDescription, BUTTON_ENTITIES


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    LOGGER.debug(f"BUTTON async_setup_entry - {config_entry}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]

    if coordinator.latestData.get('api_configuration', {}).get('IN_LocalAPIWriteActive', '0') == '1':
        entities = []
        for description in BUTTON_ENTITIES:
            if description.tag.type == Platform.BUTTON:
                entity = SonnenbatterieButton(coordinator, description)
                entities.append(entity)

        async_add_entities(entities)
    else:
        LOGGER.info(f"JSON-API write access not enabled - disabling BUTTON functions")

class SonnenbatterieButton(SonnenButtonEntity, ButtonEntity):

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieButtonEntityDescription):
        super().__init__(coordinator, description)


    async def async_press(self, **kwargs) -> None:
        tag = self.entity_description.tag
        match tag.key:
            case "button_reset_all":
                await self.coordinator.sbconn.sb2.charge_battery(0)
                await self.coordinator.sbconn.sb2.discharge_battery(0)
            case "button_reset_charge":
                await self.coordinator.sbconn.sb2.charge_battery(0)
            case "button_reset_discharge":
                await self.coordinator.sbconn.sb2.discharge_battery(0)

        await self.coordinator.async_request_refresh()
        return None
