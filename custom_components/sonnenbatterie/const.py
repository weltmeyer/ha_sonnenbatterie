import logging
from typing import Final

from homeassistant.const import Platform

SONNENBATTERIE_ISSUE_URL: Final = "https://github.com/weltmeyer/ha_sonnenbatterie/issues"

CONF_SERIAL_NUMBER = "serial_number"

ATTR_SONNEN_DEBUG = "sonnenbatterie_debug"
DOMAIN = "sonnenbatterie"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_SONNEN_DEBUG = False

LOGGER = logging.getLogger(__package__)

""" Limited to those that can be changed safely """
CONF_CONFIG_ITEMS = [
    "EM_OperatingMode",
    "EM_ToU_Schedule",
    "EM_USOC"
]

CONF_OPERATING_MODES = [
    "manual",
    "automatic",
    "timeofuse"
]

CONF_CHARGE_WATT  = "power"
CONF_COORDINATOR = "coordinator"
CONF_INVERTER_MAX = "inverter_max"
CONF_SERVICE_ITEM = "item"
CONF_SERVICE_MODE = "mode"
CONF_SERVICE_SCHEDULE = "schedule"
CONF_SERVICE_VALUE = "value"

PLATFORMS = [ Platform.SENSOR ]

SB_OPERATING_MODES: Final = {
    "manual": 1,
    "automatic": 2,
    "expansion": 6,
    "timeofuse": 10
}

# rustydust_241227: doesn't seem to be used anywhere
# def flatten_obj(prefix, seperator, obj):
#     result = {}
#     for field in obj:
#         val = obj[field]
#         val_prefix = prefix + seperator + field
#         if type(val) is dict:
#             sub = flatten_obj(val_prefix, seperator, val)
#             result.update(sub)
#         else:
#             result[val_prefix] = val
#     return result
