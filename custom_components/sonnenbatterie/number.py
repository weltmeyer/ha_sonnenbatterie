from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LOGGER
from .coordinator import SonnenbatterieCoordinator
from .entities import (
    NUMBER_ENTITIES,
    SonnenbatterieNumberEntityDescription,
    SonnenNumberEntity,
)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    LOGGER.debug(f"NUMBER - async_setup_entry: {config_entry}")
    coordinator = config_entry.runtime_data.coordinator
    # await coordinator.async_refresh()

    if coordinator.is_slave:
        # controlled by the cascade's master: read-only
        LOGGER.info(f"cascade slave {coordinator.serial} - no NUMBER entities")
        return

    if coordinator.latestData.get('api_configuration',{}).get('IN_LocalAPIWriteActive', '0') == '1':

        max_power = config_entry.runtime_data.inverter_max
        entities = []
        for description in NUMBER_ENTITIES:
            if description.tag.type == Platform.NUMBER:
                entity = SonnenbatterieNumber(coordinator, description, max_power)
                entities.append(entity)
        async_add_entities(entities)

    else:
        LOGGER.info("JSON-API write access not enabled - disabling NUMBER functions")

class SonnenbatterieNumber(SonnenNumberEntity, NumberEntity):

    def __init__(self, coordinator: SonnenbatterieCoordinator, description: SonnenbatterieNumberEntityDescription, max_power: int) -> None:
        super().__init__(coordinator, description)
        # LOGGER.debug(f"SonnenbatterieNumberEntity: {description}")
        if description.key == "battery_reserve":
            self._max_power = 100
        else:
            self._max_power = max_power

    @property
    def native_max_value(self) -> int:
        return self._max_power

    @property
    def native_value(self):
        tag = self.entity_description.tag
        if tag.key == "battery_reserve":
            # the reserve can be read back from the configurations; before,
            # the slider started at 0 until it was set from HA
            try:
                return int(self.coordinator.latestData.get(tag.section, {})[tag.property])
            except (KeyError, TypeError, ValueError):
                return None
        # the charge/discharge setpoint is write-only: show the last one
        # written (also by the reset buttons and the actions), 0 before that
        return self.coordinator.setpoints.get(tag.key, 0)

    async def async_set_native_value(self, value):
        LOGGER.debug(f"NUMBER - async_set_native_value: {value} - {type(value)}")
        tag = self.entity_description.tag
        if tag.writable:
            # serialized, session-safe, retried once, then a light refresh
            # (external controllers write every few seconds; a full refresh
            # per write would overload the battery)
            await self.coordinator.async_write_setpoint(tag.key, value)
