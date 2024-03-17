from .const import *
from .coordinator import SonnenBatterieCoordinator

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.typing import StateType

# pylint: disable=no-name-in-module
from sonnenbatterie import sonnenbatterie
from collections.abc import Callable
from dataclasses import dataclass

# pylint: enable=no-name-in-module

from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
    CONF_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SonnenbatterieSensorEntityDescription(SensorEntityDescription):
    """Describes Example sensor entity."""

    exists_fn: Callable[[SonnenBatterieCoordinator], bool] = lambda _: True
    value_fn: Callable[[SonnenBatterieCoordinator], StateType]


SENSORS: tuple[SonnenbatterieSensorEntityDescription, ...] = (
    SonnenbatterieSensorEntityDescription(
        key="status_consumption_w",
        # translation_key="total_cleaned_area",  # TODO use translations instead of hard-coded name
        name="Current grid consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda coordinator: coordinator.latestData["status"]["Consumption_W"],
        exists_fn=lambda coordinator: bool(
            coordinator.latestData["status"]["Consumption_W"]
        ),
    ),
)


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    ## we dont have anything special going on.. unload should just work, right?
    ##bridge = hass.data[DOMAIN].pop(entry.data['host'])
    return


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    LOGGER.info("SETUP_ENTRY")
    # await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    username = config_entry.data.get(CONF_USERNAME)
    password = config_entry.data.get(CONF_PASSWORD)
    ip_address = config_entry.data.get(CONF_IP_ADDRESS)
    update_interval_seconds = config_entry.options.get(CONF_SCAN_INTERVAL)
    debug_mode = config_entry.options.get(ATTR_SONNEN_DEBUG)

    def _internal_setup(_username, _password, _ip_address):
        return sonnenbatterie(_username, _password, _ip_address)

    sonnenInst = await hass.async_add_executor_job(
        _internal_setup, username, password, ip_address
    )
    update_interval_seconds = update_interval_seconds or 1
    LOGGER.info("{0} - UPDATEINTERVAL: {1}".format(DOMAIN, update_interval_seconds))

    """ The Coordinator is called from HA for updates from API """
    coordinator = SonnenBatterieCoordinator(
        hass,
        sonnenInst,
        update_interval_seconds,
        ip_address,
        debug_mode,
        config_entry.entry_id,
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        SonnenbatterieSensor(coordinator=coordinator, entity_description=description)
        for description in SENSORS
        # if description.exists_fn(coordinator=coordinator)
    )

    LOGGER.info("Init done")
    return True


class SonnenbatterieSensor(CoordinatorEntity[SonnenBatterieCoordinator], SensorEntity):
    _attr_should_poll = False
    entity_description: SonnenbatterieSensorEntityDescription

    def __init__(
        self,
        coordinator: SonnenBatterieCoordinator,
        entity_description: SonnenbatterieSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.entity_description = entity_description
        self._attr_device_info = coordinator.device_info
        # FIXME find a way to automatically prefix name with device name
        self._attr_name = f"{DOMAIN}_{self.coordinator.serial} {self.entity_description.name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        # return f"{self.coordinator.device_id}-{self.entity_description.key}"  # FIXME should be converted to this, but HA will create new entities after entity change
        return (
            f"sensor.{DOMAIN}_{self.coordinator.serial}_{self.entity_description.key}"
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator)
