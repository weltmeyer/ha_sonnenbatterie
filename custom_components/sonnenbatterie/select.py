from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_COORDINATOR, SonnenbatterieCoordinator, SonnenBaseEntity
from .const import DOMAIN, LOGGER
from .select_entities import SELECT_ENTITIES


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_entity_cb: AddEntitiesCallback
) -> None:
    LOGGER.debug(f"SELECT async_setup_entry: {config_entry}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]

    entities = []
    for description in SELECT_ENTITIES:
        entity = SonnenBatterieSelect(coordinator, description)
        entities.append(entity)

    """
    description = SonnenbatterieSelectEntityDescription(
        key="select_test",
        name="Sonnenbatterie_Select",
        icon="mdi:select",
        tag="sru_select",
        max=config_entry.data.get(CONF_INVERTER_MAX),
        min=0,
        device_class=SensorDeviceClass.POWER,
        unit_of_measurement="W",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=True,
        options=SB_OPERATING_MODES
    )
    entity = SonnenBatterieSelect(coordinator, description)
    entities.append(entity)
    """

    async_entity_cb(entities)



class SonnenBatterieSelect(SonnenBaseEntity, SelectEntity):
    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieSelectEntityDescription):
        super().__init__(coordinator=coordinator, description=description)

    @property
    def current_option(self) -> str | None:
        LOGGER.debug(f"SELECT current_option: {self.coordinator.latestData}")
        return None

    async def async_select_option(self, option: str) -> None:
        LOGGER.debug(f"SELECT async_select_option: {option}")

