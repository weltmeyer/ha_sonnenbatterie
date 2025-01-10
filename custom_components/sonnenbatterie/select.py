from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_COORDINATOR, SonnenbatterieCoordinator, SB_OPERATING_MODES_NUM
from .const import DOMAIN, LOGGER, SB_OPERATING_MODES
from .entities import SonnenSelectEntity
from .select_entities import SELECT_ENTITIES, SonnenbatterieSelectEntityDescription


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_entity_cb: AddEntitiesCallback
) -> None:
    LOGGER.debug(f"SELECT async_setup_entry: {config_entry}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]

    entities = []
    for description in SELECT_ENTITIES:
        LOGGER.debug(f"SELECT async_setup_entry: {description}")
        entity = SonnenBatterieSelect(coordinator, description)
        entities.append(entity)

    async_entity_cb(entities)


class SonnenBatterieSelect(SonnenSelectEntity, SelectEntity):
    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSelectEntityDescription):
        super().__init__(coordinator=coordinator, description=description)

    @property
    def current_option(self) ->  str | list[str] | None:
        tag = self.entity_description.tag
        LOGGER.debug(f"SELECT current_option: {self.options} | {self.coordinator.latestData[tag.section][tag.property]}")
        value = self.coordinator.latestData[tag.section][tag.property]
        return SB_OPERATING_MODES_NUM[value] or "unknown"

    async def async_select_option(self, option: str) -> None:
        tag = self.entity_description.tag
        # Check if we actually can change the setting
        if tag.writable:
            match tag.section:
                case "configurations":
                    match tag.key:
                        case "operating_mode":
                            await self.coordinator.sbconn.sb2.set_operating_mode(SB_OPERATING_MODES[option])
        return None
