from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType

from . import CONF_COORDINATOR
from .const import (
    DOMAIN,
    LOGGER,
)
from .coordinator import SonnenbatterieCoordinator
from .entities import SonnenBaseEntity

from .sensor_list import (
    SENSORS,
    V1_ONLY_SENSOR_KEYS,
    generate_powermeter_sensors, SonnenbatterieSensorEntityDescription
)


# rustydust_241227: this doesn't seem to be used anywhere
# async def async_unload_entry(hass, entry):
#     """Unload a config entry."""
#     ## we dont have anything special going on.. unload should just work, right?
#     ##bridge = hass.data[DOMAIN].pop(entry.data['host'])
#     return


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    LOGGER.debug(f"SENSOR async_setup_entry - {config_entry.data}")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]

    # await coordinator.async_refresh()

    if coordinator._token_only:
        # These sensors are never created in API-key-only mode, but entries from
        # an earlier run (e.g. login mode) would otherwise stay in the registry
        # as permanently unavailable entities.
        registry = er.async_get(hass)
        for key in V1_ONLY_SENSOR_KEYS:
            unique_id = f"sensor.sonnenbatterie_{coordinator.serial}_{key}"
            if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
                LOGGER.debug(f"Removing stale v1-only entity {entity_id}")
                registry.async_remove(entity_id)

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in SENSORS
        if description.value_fn(coordinator) is not None
    )

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in generate_powermeter_sensors(_coordinator=coordinator)
    )

    return True


class SonnenbatterieSensor(SonnenBaseEntity, SensorEntity, RestoreEntity):
    """Represent a SonnenBatterie sensor."""

    # --- now set in SonnenBaseEntity ---
    # entity_description: SonnenbatterieSensorEntityDescription
    # _attr_should_poll = False
    # _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SonnenbatterieCoordinator,
        entity_description: SonnenbatterieSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator=coordinator, description=entity_description)
        # --- now set in SonnenBaseEntity
        # self.coordinator = coordinator
        # self.entity_description = entity_description

        # self._attr_device_info = coordinator.device_info
        # self._attr_translation_key = (
        #     tkey
        #     if (tkey := entity_description.translation_key)
        #   else entity_description.key
        # )
        if entity_description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = entity_description.suggested_display_precision
        elif entity_description.state_class is not None:
            # Numeric (measurement) sensors without an explicit precision default
            # to whole numbers. Sensors with neither a state_class nor a
            # suggested_display_precision are non-numeric (plain text/enum
            # values) - forcing a precision on those makes Home Assistant treat
            # them as numeric and crash when the value isn't a number.
            self._attr_suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        # legacy support / prevent breaking changes
        key = self.entity_description.legacy_key or self.entity_description.key
        return f"sensor.sonnenbatterie_{self.coordinator.serial}_{key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator)
