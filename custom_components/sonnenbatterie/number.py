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
    # await coordinator.async_refresh()

    if coordinator.latestData.get('api_configuration',{}).get('IN_LocalAPIWriteActive', '0') == '1':

        max_power = int(hass.data[DOMAIN][config_entry.entry_id][CONF_INVERTER_MAX])
        entities = []
        for description in NUMBER_ENTITIES:
            if description.tag.type == Platform.NUMBER:
                entity = SonnenbatterieNumber(coordinator, description, max_power)
                entities.append(entity)
        async_add_entities(entities)

    else:
        LOGGER.info(f"JSON-API write access not enabled - disabling NUMBER functions")

class SonnenbatterieNumber(SonnenNumberEntity, NumberEntity):
    _attr_native_value: int = 0

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

    async def async_set_native_value(self, value):
        LOGGER.debug(f"NUMBER - async_set_native_value: {value} - {type(value)}")
        tag = self.entity_description.tag
        if tag.writable:
            # Robust write: serialized (single-request webserver), session-safe
            # (ensures a session / uses the static Auth-Token), retried once on a
            # transient 401/timeout, then a LIGHT refresh (external controllers
            # write every few seconds; a full refresh per write overloads it).
            await self.coordinator.async_write_setpoint(tag.key, value)
            # Optimistic state: the sonnen charge/discharge setpoint is WRITE-ONLY
            # (the API has no read-back of the current target), so without this the
            # entity kept its class default 0 forever and never reflected a command.
            # External controllers (e.g. SEA) read the setpoint back for their trace
            # and logged "invalid number state: unknown" / a stale 0. Only set AFTER
            # a successful write, so a failing write never fakes a value.
            self._attr_native_value = value
            self.async_write_ha_state()
        return None
