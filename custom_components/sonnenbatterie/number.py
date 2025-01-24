from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonnenbatterieCoordinator, CONF_INVERTER_MAX
from .const import LOGGER, CONF_COORDINATOR, DOMAIN
from .entities import SonnenNumberEntity, SonnenbatterieNumberEntityDescription, NUMBER_ENTITIES


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    LOGGER.debug(f"NUMBER - async_setup_entry: {config_entry}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]
    await coordinator.async_refresh()

    max_power = int(hass.data[DOMAIN][config_entry.entry_id][CONF_INVERTER_MAX])
    entities = []
    for description in NUMBER_ENTITIES:
        if description.tag.type == Platform.NUMBER:
            entity = SonnenbatterieNumber(coordinator, description, max_power)
            entities.append(entity)
    async_add_entities(entities)

class SonnenbatterieNumber(SonnenNumberEntity, NumberEntity):
    _attr_native_value: int = 0

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieNumberEntityDescription, max_power: int) -> None:
        super().__init__(coordinator, description)
        LOGGER.debug(f"SonnenbatterieNumberEntity: {description}")
        if description.key == "battery_reserve":
            self._max_power = 100
        else:
            self._max_power = max_power

    @property
    def native_max_value(self) -> int:
        return self._max_power

    async def async_set_native_value(self, value):
        LOGGER.debug(f"NUMBER - async_set_native_value: {value} - {type(value)}")
        tag = self.entity_description.tag
        if tag.writable:
            match tag.key:
                case "number_charge":
                    await self.coordinator.sbconn.sb2.charge_battery(int(value))
                case "number_discharge":
                    await self.coordinator.sbconn.sb2.discharge_battery(int(value))
                case "battery_reserve":
                    await self.coordinator.sbconn.sb2.set_battery_reserve(int(value))
            await self.coordinator.async_request_refresh()
        return None
