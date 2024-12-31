from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)

from homeassistant.helpers.typing import StateType

from .coordinator import SonnenBatterieCoordinator
from sonnenbatterie import AsyncSonnenBatterie
from .const import (
    ATTR_SONNEN_DEBUG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    logging,
)
from .sensor_list import (
    SonnenbatterieSensorEntityDescription,
    SENSORS,
    generate_powermeter_sensors,
)

# rustydust_241227: this doesn't seem to be used anywhere
# async def async_unload_entry(hass, entry):
#     """Unload a config entry."""
#     ## we dont have anything special going on.. unload should just work, right?
#     ##bridge = hass.data[DOMAIN].pop(entry.data['host'])
#     return


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    LOGGER.debug("SETUP_ENTRY")
    username = config_entry.data.get(CONF_USERNAME)
    password = config_entry.data.get(CONF_PASSWORD)
    ip_address = config_entry.data.get(CONF_IP_ADDRESS)
    update_interval_seconds = config_entry.data.get(CONF_SCAN_INTERVAL)
    debug_mode = config_entry.data.get(ATTR_SONNEN_DEBUG)

    sonnen_inst = await hass.async_add_executor_job(
        AsyncSonnenBatterie, username, password, ip_address
    )

    update_interval_seconds = update_interval_seconds or DEFAULT_SCAN_INTERVAL
    LOGGER.debug(f"{DOMAIN} - UPDATEINTERVAL: {update_interval_seconds}")

    """ The Coordinator is called from HA for updates from API """
    coordinator = SonnenBatterieCoordinator(
        hass,
        sonnen_inst,
        update_interval_seconds,
        ip_address,
        debug_mode,
        config_entry.entry_id,
    )

    if config_entry.state == ConfigEntryState.SETUP_IN_PROGRESS:
        await coordinator.async_config_entry_first_refresh()
    else:
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


class SonnenbatterieSensor(CoordinatorEntity[SonnenBatterieCoordinator], SensorEntity):
    """Represent an SonnenBatterie sensor."""

    entity_description: SonnenbatterieSensorEntityDescription
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: SonnenBatterieCoordinator,
        entity_description: SonnenbatterieSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.entity_description = entity_description

        self._attr_device_info = coordinator.device_info
        self._attr_translation_key = (
            tkey
            if (tkey := entity_description.translation_key)
            else entity_description.key
        )
        if precision := entity_description.suggested_display_precision:
            self._attr_suggested_display_precision = precision

        self.entity_id = f"sensor.sonnenbatterie_{self.coordinator.serial}_{self.entity_description.key}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        # return f"{self.coordinator.serial}-{self.entity_description.key}"

        # legacy support / prevent breaking changes
        key = self.entity_description.legacy_key or self.entity_description.key
        return f"sensor.sonnenbatterie_{self.coordinator.serial}_{key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator)
