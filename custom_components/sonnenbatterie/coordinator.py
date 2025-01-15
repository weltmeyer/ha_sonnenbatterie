import traceback
from datetime import timedelta
from time import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME, CONF_PASSWORD, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from sonnenbatterie import AsyncSonnenBatterie

from custom_components.sonnenbatterie import LOGGER, DOMAIN, ATTR_SONNEN_DEBUG, CONF_SERIAL_NUMBER


class SonnenbatterieCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Sonnenbatteries data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, serial: str) -> None:
        LOGGER.info(f"Initializing SonnenbatterieCoordinator: {config_entry.data}")

        """ private attributes """
        self._batt_reserved_factor = 7.0    # fixed value, reseved percentage of total installed power for internal use
        self._config_entry = config_entry
        self._fullLogsAlreadySent = False
        self._last_error = None
        self._last_login = 0

        """ public attributes """
        self.latestData = {}
        self.name = config_entry.title
        self.serial = serial
        self.sbconn = AsyncSonnenBatterie(username=self._config_entry.data[CONF_USERNAME],
                                          password=self._config_entry.data[CONF_PASSWORD],
                                          ipaddress=self._config_entry.data[CONF_IP_ADDRESS])

        super().__init__(hass,
                         LOGGER,
                         name=DOMAIN,
                         update_interval=timedelta(seconds=config_entry.data.get(CONF_SCAN_INTERVAL, 30)))

    @property
    def device_info(self) -> DeviceInfo:
        system_data = self.latestData["battery_system"]["battery_system"]
        system_info = self.latestData["system_data"]

        # noinspection HttpUrlsUsage
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            configuration_url=f"http://{self._config_entry.data[CONF_IP_ADDRESS]}/",
            manufacturer="Sonnen",
            model=system_info.get("ERP_ArticleName", "unknown"),
            name=f"{DOMAIN} {self.serial}",
            serial_number=f"{self.serial}",
            sw_version=f"{system_data['software'].get('software_version', 'unknown')} ({system_data['software'].get('firmware_version', 'unknown')})",
            hw_version=f"{system_data['system'].get('hardware_version', 'unknown'):.1f}",
        )

    def populate_battery_info(self):
        """ some manually calculated values """
        batt_module_capacity = int(
            self.latestData["battery_system"]["battery_system"]["system"]["storage_capacity_per_module"]
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
            total_installed_capacity * (self._batt_reserved_factor / 100.0)
        )
        self.latestData["battery_info"]["remaining_capacity"] = remaining_capacity = (
            int(total_installed_capacity * self.latestData["status"]["RSOC"]) / 100.0
        )
        self.latestData["battery_info"]["remaining_capacity_usable"] = max(
            0, int(remaining_capacity - reserved_capacity)
        )

    async def _async_update_data(self):
        """Populate self.latestdata"""
        if time() - self._last_login > 60:
            try:
                await self.sbconn.logout()
            except:
                pass
            await self.sbconn.login()
            self._last_login = time()

        LOGGER.debug(f"COORDINATOR - async_update_data: {self._config_entry.data}")
        try:
            result = await self.sbconn.get_battery()
            self.latestData["battery"] = result

            result = await self.sbconn.get_batterysystem()
            self.latestData["battery_system"] = result

            result = await self.sbconn.get_inverter()
            self.latestData["inverter"] = result

            result = await self.sbconn.get_powermeter()
            self.latestData["powermeter"] = result

            result = await self.sbconn.get_status()
            self.latestData["status"] = result

            result = await self.sbconn.get_systemdata()
            self.latestData["system_data"] = result

            result = await self.sbconn.sb2.get_configurations()
            self.latestData["configurations"] = result

            self._last_error = None

        except Exception as e:
            LOGGER.debug(traceback.format_exc())
            if self._last_error is not None:
                LOGGER.info(traceback.format_exc() + " ... might be maintenance window")
                elapsed = time() - self._last_error
                if elapsed > 180:
                    LOGGER.error(
                        f"Unable to connecto to Sonnenbatteries at {self._config_entry.data[CONF_IP_ADDRESS]} for {elapsed} seconds. Please check! [{e}]")
            else:
                self._last_error = time()

        # Fixup for older models
        if isinstance(self.latestData.get("powermeter"), dict):
            # noinspection PyBroadException
            try:
                # some new firmware of sonnenbatterie seems to send a dictionary, but we work with a list, so reformat :)
                new_powermeters = []
                for index, dictIndex in enumerate(self.latestData["powermeter"]):
                    new_powermeters.append(self.latestData["powermeter"][dictIndex])
                self.latestData["powermeter"] = new_powermeters
            except:
                e = traceback.format_exc()
                LOGGER.error(e)

        if self._config_entry.data.get(ATTR_SONNEN_DEBUG, False):
            self.send_all_data_to_log()

        self.populate_battery_info()

    async def fetch_sonnenbatterie_on_startup(self):
        """Fetch all config items from Sonnenbatterie."""
        LOGGER.debug(f"Fetching Sonnenbatteries on startup")
        await self._async_update_data()

    def send_all_data_to_log(self):
        """
        Since we're in "debug" mode, send all data to the log, so we don't have to search for the
        variable we're looking for if it's not where we expect it to be
        """
        if not self._fullLogsAlreadySent:
            LOGGER.warning(f"Powermeter data:\n{self.latestData['powermeter']}")
            LOGGER.warning(f"Battery system data:\n{self.latestData['battery_system']}")
            LOGGER.warning(f"Inverted:\n{self.latestData['inverter']}")
            LOGGER.warning(f"System data:\n{self.latestData['system_data']}")
            LOGGER.warning(f"Status:\n{self.latestData['status']}")
            LOGGER.warning(f"Battery:\n{self.latestData['battery']}")
            self._fullLogsAlreadySent = True
