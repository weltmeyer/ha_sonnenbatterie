from homeassistant.components.binary_sensor import BinarySensorEntity

from . import CONF_COORDINATOR
from .const import DOMAIN, LOGGER
from .coordinator import SonnenbatterieCoordinator
from .entities import SonnenBaseEntity

from .binary_sensor_list import (
    BINARY_SENSORS,
    SonnenbatterieBinarySensorEntityDescription,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the binary_sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]
    LOGGER.debug(f"BINARY_SENSOR async_setup_entry - {coordinator.safe_config}")

    async_add_entities(
        SonnenbatterieBinarySensor(coordinator=coordinator, entity_description=description)
        for description in BINARY_SENSORS
        if description.value_fn(coordinator) is not None
    )

    return True


class SonnenbatterieBinarySensor(SonnenBaseEntity, BinarySensorEntity):
    """Represent a SonnenBatterie binary sensor."""

    def __init__(
        self,
        coordinator: SonnenbatterieCoordinator,
        entity_description: SonnenbatterieBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator=coordinator, description=entity_description)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"binary_sensor.sonnenbatterie_{self.coordinator.serial}_{self.entity_description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the fault/condition is present."""
        return self.entity_description.value_fn(self.coordinator)
