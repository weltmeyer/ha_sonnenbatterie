from homeassistant.components.binary_sensor import BinarySensorEntity

from . import CONF_COORDINATOR
from .const import DOMAIN, LOGGER
from .coordinator import SonnenbatterieCoordinator
from .entities import SonnenBaseEntity

from .binary_sensor_list import (
    BINARY_SENSORS,
    SonnenbatterieBinarySensorEntityDescription,
    generate_powermeter_binary_sensors,
    io_pin_description,
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

    # a cascade's slave has no (connected) meters
    if not coordinator.is_slave:
        async_add_entities(
            SonnenbatterieBinarySensor(coordinator=coordinator, entity_description=description)
            for description in generate_powermeter_binary_sensors(coordinator)
        )

    # Digital I/O pins (/api/v2/io). Which pins have a function (the "usage"
    # label, e.g. "DC-FAN") depends on the installation, so the entities are
    # built from the data instead of from a fixed list. Unassigned pins
    # (empty usage) are skipped. All are disabled by default.
    io_data = coordinator.latestData.get("io")
    if isinstance(io_data, dict):
        async_add_entities(
            SonnenbatterieIoBinarySensor(
                coordinator=coordinator,
                entity_description=io_pin_description(pin, state["usage"]),
                pin=pin,
            )
            for pin, state in sorted(io_data.items())
            if isinstance(state, dict) and state.get("usage") and state.get("status") is not None
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


class SonnenbatterieIoBinarySensor(SonnenbatterieBinarySensor):
    """A digital input/output pin of the battery controller (/api/v2/io)."""

    def __init__(
        self,
        coordinator: SonnenbatterieCoordinator,
        entity_description: SonnenbatterieBinarySensorEntityDescription,
        pin: str,
    ) -> None:
        super().__init__(coordinator=coordinator, entity_description=entity_description)
        self._pin = pin

    @property
    def _pin_state(self) -> dict:
        state = (self.coordinator.latestData.get("io") or {}).get(self._pin)
        return state if isinstance(state, dict) else {}

    @property
    def extra_state_attributes(self) -> dict:
        return {"pin": self._pin, "connector": self._pin_state.get("connector")}
