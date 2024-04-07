"""The data update coordinator for OctoPrint."""

import traceback

from .const import DOMAIN, LOGGER, logging
from datetime import timedelta

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from sonnenbatterie import sonnenbatterie
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SonnenBatterieCoordinator(DataUpdateCoordinator):
    """The SonnenBatterieCoordinator class."""

    def __init__(
        self,
        hass: HomeAssistant,
        sb_inst: sonnenbatterie,
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

        self.sbInst: sonnenbatterie = sb_inst
        self.meterSensors = {}
        self.update_interval_seconds = update_interval_seconds
        self.ip_address = ip_address
        self.debug = debug_mode
        self.fullLogsAlreadySent = False

        # fixed value, percentage of total installed power reserved for
        # internal battery system purposes
        self.batt_reserved_factor = 7.0

        # placeholders, will be filled later
        self.serial = ""

    @property
    def device_info(self) -> DeviceInfo:
        system_data = self.latestData["system_data"]

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            configuration_url=f"http://{self.ip_address}/",
            manufacturer="Sonnen",
            model=system_data.get("ERP_ArticleName", "unknown"),
            name=f"{DOMAIN} {system_data.get('DE_Ticket_Number', 'unknown')}",
            sw_version=system_data.get("software_version", "unknown"),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:  # ignore errors here, may be transient
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

        if self.serial == "":
            if (
                serial := self.latestData.get("system_data", {}).get("DE_Ticket_Number")
            ) is not None:
                self.serial = serial
            else:
                LOGGER.warning("Unable to retrieve sonnenbatterie serial number.")
                self.serial = "UNKNOWN"

        """ some manually calculated values """
        batt_module_capacity = int(
            self.latestData["battery_system"]["battery_system"]["system"][
                "storage_capacity_per_module"
            ]
        )
        batt_module_count = int(self.latestData["battery_system"]["modules"])

        if self.latestData["status"]["BatteryCharging"]:
            battery_current_state = "charging"
        elif self.latestData["status"]["BatteryDischarging"]:
            battery_current_state = "discharging"
        else:
            battery_current_state = "standby"

        self.latestData["battery_info"] = {}
        self.latestData["battery_info"]["current_state"] = battery_current_state
        self.latestData["battery_info"][
            "total_installed_capacity"
        ] = total_installed_capacity = int(batt_module_count * batt_module_capacity)
        self.latestData["battery_info"]["reserved_capacity"] = reserved_capacity = int(
            total_installed_capacity * (self.batt_reserved_factor / 100.0)
        )
        self.latestData["battery_info"]["remaining_capacity"] = remaining_capacity = (
            int(total_installed_capacity * self.latestData["status"]["RSOC"]) / 100.0
        )
        self.latestData["battery_info"]["remaining_capacity_usable"] = max(
            0, int(remaining_capacity - reserved_capacity)
        )

    def send_all_data_to_log(self):
        """
        Since we're in "debug" mode, send all data to the log, so we don't have to search for the
        variable we're looking for if it's not where we expect it to be
        """
        if not self.fullLogsAlreadySent:
            LOGGER.warning(f"Powermeter data:\n{self.latestData['powermeter']}")
            LOGGER.warning(f"Battery system data:\n{self.latestData['battery_system']}")
            LOGGER.warning(f"Inverted:\n{self.latestData['inverter']}")
            LOGGER.warning(f"System data:\n{self.latestData['system_data']}")
            LOGGER.warning(f"Status:\n{self.latestData['status']}")
            LOGGER.warning(f"Battery:\n{self.latestData['battery']}")
            self.fullLogsAlreadySent = True
