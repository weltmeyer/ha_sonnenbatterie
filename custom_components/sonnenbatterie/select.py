from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_COORDINATOR, SonnenbatterieCoordinator, SB_OPERATING_MODES_NUM
from .const import DOMAIN, LOGGER, SB_OPERATING_MODES
from .entities import SonnenSelectEntity, SELECT_ENTITIES, SonnenbatterieSelectEntityDescription
from .service import async_set_operating_mode


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_entity_cb: AddEntitiesCallback
) -> None:
    LOGGER.debug(f"SELECT async_setup_entry: {config_entry}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]

    if coordinator.is_slave:
        # controlled by the cascade's master: read-only
        LOGGER.info(f"cascade slave {coordinator.serial} - no SELECT entities")
        return

    if coordinator.latestData.get('api_configuration',{}).get('IN_LocalAPIWriteActive', '0') == '1':
        # await coordinator.async_refresh()

        entities = []
        for description in SELECT_ENTITIES:
            entity = SonnenBatterieSelect(coordinator, description)
            entities.append(entity)

        async_entity_cb(entities) if len(entities) > 0 else None

    else:
        LOGGER.info(f"JSON-API write access not enabled - disabling SELECT functions")

class SonnenBatterieSelect(SonnenSelectEntity, SelectEntity):
    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSelectEntityDescription):
        super().__init__(coordinator=coordinator, description=description)

    @property
    def current_option(self) ->  str | list[str] | None:
        tag = self.entity_description.tag
        # the status is read on every update, the configurations only every
        # few: the status' OperatingMode shows a change right away (both
        # always change together), the configuration is the fallback
        value = (self.coordinator.latestData.get("status", {}).get("OperatingMode")
                 or self.coordinator.latestData.get(tag.section, {}).get(tag.property))
        # modes that can't be selected (4 testing, 6 module extension) or
        # unknown ones show as unknown; the operating mode sensor names them
        return SB_OPERATING_MODES_NUM.get(str(value))

    async def async_select_option(self, option: str) -> None:
        tag = self.entity_description.tag
        # Check if we actually can change the setting
        if tag.writable:
            match tag.section:
                case "configurations":
                    match tag.key:
                        case "select_operating_mode":
                            await async_set_operating_mode(self.coordinator.sbconn, SB_OPERATING_MODES[option])
                            await self.coordinator.async_request_refresh()

        return None
