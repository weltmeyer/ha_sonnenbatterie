import time

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import callback
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
    ENERGY_SENSORS,
    SENSORS,
    generate_powermeter_sensors, generate_pv_string_sensors, SonnenbatterieSensorEntityDescription
)


# rustydust_241227: this doesn't seem to be used anywhere
# async def async_unload_entry(hass, entry):
#     """Unload a config entry."""
#     ## we dont have anything special going on.. unload should just work, right?
#     ##bridge = hass.data[DOMAIN].pop(entry.data['host'])
#     return


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]
    LOGGER.debug(f"SENSOR async_setup_entry - {coordinator.safe_config}")

    # await coordinator.async_refresh()

    # a cascade's slave has no meters and no cascade-wide settings: skip
    # those sensors and its (unconnected) powermeters
    slave = coordinator.is_slave
    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in SENSORS
        if (description.on_slave or not slave)
        and (description.exists_fn(coordinator) if description.exists_fn
             else description.value_fn(coordinator) is not None)
    )

    if not slave:
        async_add_entities(
            SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
            for description in generate_powermeter_sensors(_coordinator=coordinator)
        )

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in generate_pv_string_sensors(_coordinator=coordinator)
    )

    if not slave:
        async_add_entities(
            SonnenbatterieEnergySensor(coordinator=coordinator, entity_description=description)
            for description in ENERGY_SENSORS
        )

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

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)


class SonnenbatterieEnergySensor(SonnenbatterieSensor, RestoreSensor):
    """Energy (kWh) summed up from a power value (W), for the energy dashboard.

    On every coordinator update, the power of the previous update is counted
    for the time since then (left Riemann sum: the battery reports the power
    of that moment, which is assumed to last until the next report). Failed
    updates and the last known values kept during an outage are skipped; the
    last fresh power is counted up to the next fresh report if that comes
    within MAX_GAP or a few update intervals, after failed updates (e.g. the
    nightly maintenance window) also allowing for the coordinator's back-off.
    Longer gaps (HA not running, a real outage) are not counted, instead of
    multiplying a stale value. The total is restored after a restart.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    MAX_GAP = 300           # seconds
    MAX_GAP_INTERVALS = 3   # update intervals
    # after failed polls the coordinator backs off (up to MAX_BACKOFF_INTERVAL)
    # while keeping the last values (MAINTENANCE_GRACE): the first good poll
    # after the maintenance window can come that much later; plus some time
    # for the failed requests' timeouts
    OUTAGE_SLACK = 60       # seconds

    def __init__(self, coordinator, entity_description) -> None:
        super().__init__(coordinator=coordinator, entity_description=entity_description)
        self._energy = 0.0          # kWh
        self._last_power = None     # W, from the previous update
        self._last_time = None      # time.monotonic() of the previous update
        self._outage = False        # failed/stale updates since then

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._energy = float(last.native_value)
            except (TypeError, ValueError):
                LOGGER.warning(f"{self.entity_id}: can't restore {last.native_value!r}, starting at 0")
        # no time stamp survives a restart: start summing with the next update
        self._sample(time.monotonic())

    @property
    def native_value(self) -> float:
        return round(self._energy, 4)

    @property
    def available(self) -> bool:
        # the total stays valid while the battery is unreachable
        return True

    def _max_gap(self) -> float:
        interval = getattr(self.coordinator, "_base_interval", None)
        seconds = interval.total_seconds() if interval else 0
        limit = max(self.MAX_GAP, self.MAX_GAP_INTERVALS * seconds)
        if self._outage:
            # the battery didn't answer (e.g. maintenance window): allow for
            # the coordinator's back-off. Without any updates in between (HA
            # not running) the shorter limit applies.
            limit = max(limit, getattr(self.coordinator, "MAINTENANCE_GRACE", 0)
                        + max(seconds, getattr(self.coordinator, "MAX_BACKOFF_INTERVAL", 0))
                        + self.OUTAGE_SLACK)
        return limit

    def _sample(self, now: float) -> None:
        power = None
        # not the last known values kept during an outage: they would be
        # counted for the whole outage
        if self.coordinator.has_fresh_data:
            try:
                power = self.entity_description.value_fn(self.coordinator)
            except (TypeError, ValueError):
                power = None
        if power is None:
            # keep the last fresh sample: a short outage is bridged with it
            self._outage = True
            return
        if self._last_power is not None and 0 < now - self._last_time <= self._max_gap():
            self._energy += self._last_power * (now - self._last_time) / 3_600_000
        self._last_power = power
        self._last_time = now
        self._outage = False

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sample(time.monotonic())
        super()._handle_coordinator_update()
