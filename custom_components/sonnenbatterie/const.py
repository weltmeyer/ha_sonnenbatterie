import logging
import voluptuous as vol

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
    CONF_SCAN_INTERVAL,
)

LOGGER = logging.getLogger(__package__)

DOMAIN = "sonnenbatterie"
DEFAULT_SCAN_INTERVAL = 10

CONFIG_SCHEMA_A = vol.Schema(
    {
        vol.Required(CONF_USERNAME): vol.In(["User", "Installer"]),
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_IP_ADDRESS): str,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: CONFIG_SCHEMA_A},
    extra=vol.ALLOW_EXTRA,
)

ATTR_SONNEN_DEBUG = "sonnenbatterie_debug"
DEFAULT_SONNEN_DEBUG = False
PLATFORMS = ["sensor"]


def flatten_obj(prefix, seperator, obj):
    result = {}
    for field in obj:
        val = obj[field]
        val_prefix = prefix + seperator + field
        if type(val) is dict:
            sub = flatten_obj(val_prefix, seperator, val)
            result.update(sub)
        else:
            result[val_prefix] = val
    return result
