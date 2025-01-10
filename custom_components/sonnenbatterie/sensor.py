from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntryState
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

    if config_entry.state == ConfigEntryState.SETUP_IN_PROGRESS:
        LOGGER.debug(f"SENSOR {DOMAIN} - first refresh")
        await coordinator.async_config_entry_first_refresh()
    else:
        LOGGER.debug(f"SENSOR {DOMAIN} - Async Refresh")
        await coordinator.async_refresh()

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in SENSORS
        if description.value_fn(coordinator) is not None
    )

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in generate_powermeter_sensors(_coordinator=coordinator)
    )

    LOGGER.debug("Init done")
    return True


class SonnenbatterieSensor(SonnenBaseEntity, SensorEntity, RestoreEntity):
    """Represent a SonnenBatterie sensor."""

    # --- now set in SonnenBaseEntity ---
    # entity_description: SonnenbatterieSensorEntityDescription
    # _attr_should_poll = False
    # _attr_has_entity_name = True
    _attr_suggested_display_precision = 0

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
        if precision := entity_description.suggested_display_precision:
            self._attr_suggested_display_precision = precision

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
