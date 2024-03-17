import traceback

# from datetime import timedelta

from .const import *
from .mappings import SBmap

import ast

# from homeassistant.helpers.device_registry import DeviceInfo ##this seems to be the way in some of the next updates...?
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass

# pylint: disable=no-name-in-module
from sonnenbatterie import sonnenbatterie
from homeassistant.core import HomeAssistant

# pylint: enable=no-name-in-module

from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
    CONF_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SonnenBatterieCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        sb_inst: sonnenbatterie,
        async_add_entities,
        update_interval_seconds: int,
        ip_address,
        debug_mode,
        device_id,
    ):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=f"sonnenbatterie-{device_id}",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.sensor = None
        self.hass = hass
        self.latestData = {}
        self.disabledSensors = []
        self.device_id = device_id

        self.stopped = False

        # self.sensor = sensor
        self.sbInst: sonnenbatterie = sb_inst
        self.meterSensors = {}
        self.update_interval_seconds = update_interval_seconds
        self.ip_address = ip_address
        self.async_add_entities = async_add_entities
        self.debug = debug_mode
        self.fullLogsAlreadySent = False

        # fixed value, percentage of total installed power reserved for
        # internal battery system purposes
        self.reservedFactor = 7.0

        # placeholders, will be filled later
        self.serial = ""
        self.allSensorsPrefix = ""
        self.deviceName = "to be set"

    @property
    def device_info(self) -> DeviceInfo:
        system_data = self.latestData["system_data"]

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            configuration_url=f"http://{self.ip_address}/",
            manufacturer="Sonnen",
            model=system_data.get("ERP_ArticleName", "unknown"),
            name=f"{DOMAIN}_{system_data.get('DE_Ticket_Number', 'unknown')}",
            sw_version=system_data.get("software_version", "unknown"),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:  ##ignore errors here, may be transient
            self.latestData["battery"] = await self.hass.async_add_executor_job(
                self.sbInst.get_battery
            )
            self.latestData["battery_system"] = await self.hass.async_add_executor_job(
                self.sbInst.get_batterysystem
            )
            self.latestData["inverter"] = await self.hass.async_add_executor_job(
                self.sbInst.get_inverter
            )
            self.latestData["powermeter"] = await self.hass.async_add_executor_job(
                self.sbInst.get_powermeter
            )
            self.latestData["status"] = await self.hass.async_add_executor_job(
                self.sbInst.get_status
            )
            self.latestData["system_data"] = await self.hass.async_add_executor_job(
                self.sbInst.get_systemdata
            )

        except:
            e = traceback.format_exc()
            LOGGER.error(e)
        if self.debug:
            self.send_all_data_to_log()

        self.parse()

        # Create/Update the Main Sensor, named after the battery serial
        system_data = self.latestData["system_data"]
        serial = system_data["DE_Ticket_Number"]
        if self.sensor is None:
            self.sensor = SonnenBatterieSensor(
                coordinator=self,
                entity_id=f"sensor.{DOMAIN}_{serial}",
            )
            self.async_add_entities([self.sensor])

        state_display = "standby"
        if self.latestData["status"]["BatteryCharging"]:
            state_display = "charging"
        elif self.latestData["status"]["BatteryDischarging"]:
            state_display = "discharging"

        # let's do this just once
        if self.serial == "":
            if "DE_Ticket_Number" in self.latestData["system_data"]:
                self.serial = self.latestData["system_data"]["DE_Ticket_Number"]
            else:
                self.serial = "UNKNOWN"
            self.allSensorsPrefix = "sensor.{}_{}_".format(DOMAIN, self.serial)
            self.deviceName = "{}_{}".format(DOMAIN, self.serial)

        self.sensor.set_state(state_display)
        self.sensor.set_attributes(self.latestData["system_data"])
        # finish Update/Create Main Sensor

        # update all other entities/sensors
        self.add_or_update_entities()

    def parse(self):
        meters = self.latestData["powermeter"]
        battery_system = self.latestData["battery_system"]

        attr = {}
        for meter in meters:
            prefix = "{0}_{1}_{2}-".format(
                meter["direction"], meter["deviceid"], meter["channel"]
            )
            for name in meter:
                parm_name = prefix + name
                attr[parm_name] = meter[name]

        bat_sys_dict = flatten_obj("battery_system", "-", battery_system)
        attr.update(bat_sys_dict)

    def walk_entities(self, entities, parents=[], key=""):
        if "sensor" in entities:
            # only check if we haven't already disabled the sensor
            if entities["sensor"] not in self.disabledSensors:
                # check whether key exists
                lookup = self.latestData
                for section in parents:
                    if section in lookup:
                        # move down to next section
                        lookup = lookup[section]
                    else:
                        # section not found, disable sensor
                        self.disabledSensors.append(entities["sensor"])
                        LOGGER.warning(
                            "'{}' not in {} -> disabled".format(
                                entities["sensor"], "/".join(parents)
                            )
                        )
                        return

                # when we get here 'lookup' already is the value we're looking for
                # first, calculate the actual value
                if "convert" in entities:
                    try:
                        real_val = entities["convert"](lookup)
                    except:
                        LOGGER.critical(
                            "Wrong conversion info for '{}' in {} -> sending raw value".format(
                                key, "/".join(parents)
                            )
                        )
                        real_val = lookup
                else:
                    real_val = lookup

                self._add_or_update_entity(
                    "{}{}".format(self.allSensorsPrefix, entities["sensor"]),
                    entities["friendly_name"],
                    real_val,
                    entities["unit"],
                    entities["class"],
                    (
                        entities["state_class"]
                        if "state_class" in entities
                        else "measurement"
                    ),
                )

                # add alias names if needed
                if "aka" in entities:
                    for altname in entities["aka"]:
                        self._add_or_update_entity(
                            "{}{}".format(self.allSensorsPrefix, altname),
                            "{} (alias)".format(entities["friendly_name"]),
                            real_val,
                            entities["unit"],
                            entities["class"],
                        )

                # do we need to add in/out values?
                if "inout" in entities:
                    val_in = abs(real_val) if real_val < 0 else 0
                    val_out = real_val if real_val > 0 else 0
                    sensor_base = entities["sensor"][
                        : entities["sensor"].rfind("_") + 1
                    ]
                    self._add_or_update_entity(
                        "{}{}input".format(self.allSensorsPrefix, sensor_base),
                        "{} (in)".format(entities["friendly_name"]),
                        val_in,
                        entities["unit"],
                        entities["class"],
                    )
                    self._add_or_update_entity(
                        "{}{}output".format(self.allSensorsPrefix, sensor_base),
                        "{} (out)".format(entities["friendly_name"]),
                        val_out,
                        entities["unit"],
                        entities["class"],
                    )

                # do we have a text mapping?
                if "textmap" in entities:
                    tmap = ast.literal_eval(entities["textmap"])
                    if real_val in tmap:
                        tval = tmap[real_val]
                    else:
                        tval = "Unknown"
                    self._add_or_update_entity(
                        "{}{}_{}".format(
                            self.allSensorsPrefix, entities["sensor"], "text"
                        ),
                        "{} (text)".format(entities["friendly_name"]),
                        tval,
                        entities["unit"],
                        entities["class"],
                        None,
                    )
        else:
            # recursively check deeper down
            for elem in entities:
                LOGGER.info("Descending into '{}'".format(elem))
                # push current path to "stack"
                parents.append(elem)
                self.walk_entities(entities[elem], parents, elem)
                # pop path from stack to prevent ever growing path array
                parents.remove(elem)

    def _add_or_update_entity(
        self,
        entity_id,
        friendly_name,
        value,
        unit,
        device_class,
        state_class="measurement",
    ):
        if entity_id in self.meterSensors:
            sensor = self.meterSensors[entity_id]
            sensor.set_state(value)
        else:
            sensor = SonnenBatterieSensor(
                coordinator=self,
                entity_id=entity_id,
            )
            sensor.set_attributes(
                {
                    "unit_of_measurement": unit,
                    "device_class": device_class,
                    "friendly_name": friendly_name,
                    "state_class": state_class,
                }
            )
            self.async_add_entities([sensor])
            self.meterSensors[entity_id] = sensor

    def add_or_update_entities(self):
        """(almost) all sensors in one go"""
        self.walk_entities(SBmap)

        """ some manually calculated values """
        val_module_capacity = int(
            self.latestData["battery_system"]["battery_system"]["system"][
                "storage_capacity_per_module"
            ]
        )
        val_module_count = int(self.latestData["battery_system"]["modules"])
        total_installed_capacity = int(val_module_count * val_module_capacity)

        """" Battery Real Capacity Calc """
        sensor_name = "{}{}".format(self.allSensorsPrefix, "state_total_capacity_real")
        unit_name = "Wh"
        friendly_name = "Total Capacity Real"
        self._add_or_update_entity(
            sensor_name,
            friendly_name,
            total_installed_capacity,
            unit_name,
            SensorDeviceClass.ENERGY,
        )

        calc_reserved_capacity = int(
            total_installed_capacity * (self.reservedFactor / 100.0)
        )
        sensor_name = "{}{}".format(
            self.allSensorsPrefix, "state_total_capacity_usable"
        )
        unit_name = "Wh"
        friendly_name = "Total Capacity Usable"
        self._add_or_update_entity(
            sensor_name,
            friendly_name,
            total_installed_capacity - calc_reserved_capacity,
            unit_name,
            SensorDeviceClass.ENERGY,
        )

        calc_remaining_capacity = (
            int(total_installed_capacity * self.latestData["status"]["RSOC"]) / 100.0
        )
        sensor_name = "{}{}".format(
            self.allSensorsPrefix, "state_remaining_capacity_real"
        )
        unit_name = "Wh"
        friendly_name = "Remaining Capacity Real"
        self._add_or_update_entity(
            sensor_name,
            friendly_name,
            calc_remaining_capacity,
            unit_name,
            SensorDeviceClass.ENERGY,
        )

        calc_remaining_capacity_usable = max(
            0, int(calc_remaining_capacity - calc_reserved_capacity)
        )

        sensor_name = "{}{}".format(
            self.allSensorsPrefix, "state_remaining_capacity_usable"
        )
        unit_name = "Wh"
        friendly_name = "Remaining Capacity Usable"
        self._add_or_update_entity(
            sensor_name,
            friendly_name,
            calc_remaining_capacity_usable,
            unit_name,
            SensorDeviceClass.ENERGY,
        )

        """powermeter values"""
        for meter in self.latestData["powermeter"]:
            sensor_name_prefix = "{}meter_{}_{}_{}".format(
                self.allSensorsPrefix,
                meter["direction"],
                meter["deviceid"],
                meter["channel"],
            )
            sensor_name_prefix = sensor_name_prefix.lower()
            generate_sensors_for = {
                "a_l1",
                "a_l2",
                "a_l3",
                "v_l1_l2",
                "v_l1_n",
                "v_l2_l3",
                "v_l2_n",
                "v_l3_l1",
                "v_l3_n",
                "w_l1",
                "w_l2",
                "w_l3",
                "w_total",
            }

            for sensor_meter in generate_sensors_for:
                sensor_name = "{}_{}".format(sensor_name_prefix, sensor_meter)
                val = round(meter[sensor_meter], 2)
                unit_name = (sensor_meter[0] + "").upper()
                device_class = SensorDeviceClass.POWER
                if unit_name == "V":
                    device_class = SensorDeviceClass.VOLTAGE
                elif unit_name == "A":
                    device_class = SensorDeviceClass.CURRENT
                friendly_name = "{0} {1}".format(meter["direction"], sensor_meter)
                self._add_or_update_entity(
                    sensor_name, friendly_name, val, unit_name, device_class
                )

    def send_all_data_to_log(self):
        """
        Since we're in "debug" mode, send all data to the log, so we don't have to search for the
        variable we're looking for if it's not where we expect it to be
        """
        if not self.fullLogsAlreadySent:
            LOGGER.warning("Powermeter data:")
            LOGGER.warning(self.latestData["powermeter"])
            LOGGER.warning("Battery system data:")
            LOGGER.warning(self.latestData["battery_system"])
            LOGGER.warning("Inverter:")
            LOGGER.warning(self.latestData["inverter"])
            LOGGER.warning("System data:")
            LOGGER.warning(self.latestData["system_data"])
            LOGGER.warning("Status:")
            LOGGER.warning(self.latestData["status"])
            LOGGER.warning("Battery:")
            LOGGER.warning(self.latestData["battery"])
            self.fullLogsAlreadySent = True



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
        async_add_entities,
        update_interval_seconds,
        ip_address,
        debug_mode,
        config_entry.entry_id,
    )

    await coordinator.async_config_entry_first_refresh()

    LOGGER.info("Init done")
    return True


class SonnenBatterieSensorBase(
    CoordinatorEntity[SonnenBatterieCoordinator], SensorEntity
):
    _attr_should_poll = False

    def __init__(self, coordinator: SonnenBatterieCoordinator, entity_id: str) -> None:
        super().__init__(coordinator)
        self._entity_id = entity_id
        self._attr_unique_id = entity_id
        self._attr_device_info = coordinator.device_info


class SonnenBatterieSensor(SonnenBatterieSensorBase):
    """Represent an Sonnen sensor."""

    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: SonnenBatterieCoordinator, entity_id: str) -> None:
        super().__init__(coordinator, entity_id)

        self._state = None
        self.coordinator = coordinator
        self.entity_id = entity_id

        # LOGGER.info("Create Sensor {0}".format(entity_id))

    def set_state(self, state):
        """Set the state."""
        if self._state == state:
            return
        self._state = state
        if self.hass is None:
            # LOGGER.warning("hass not set, sensor: {} ".format(self.name))
            return
        self.schedule_update_ha_state()
        # try:
        # self.schedule_update_ha_state()
        # except:
        #    LOGGER.error("Failing sensor: {} ".format(self.name))

    def set_attributes(self, attributes):
        """Set the state attributes."""
        self._attributes = attributes

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    def update(self):
        LOGGER.info("update " + self.entity_id)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._attributes.get("unit_of_measurement", None)

    @property
    def device_class(self):
        """Return the device_class."""
        return self._attributes.get("device_class", None)

    @property
    def state_class(self):
        """Return the unit of measurement."""
        return self._attributes.get("state_class", None)


