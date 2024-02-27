from homeassistant.components.sensor import (
    SensorDeviceClass
)

"""
The problem we're facing is that there's no uniform reply by the v1 API.
Instead it gives out different sets of data depending on the installed
hardware.
The v2 API has a more uniform interface but doesn't give us all the data
we want. So we have to stick with v1 for the time being and try to make
a best effort when getting our values.

How it works:
Do determine what sensors your installation support please run this gist:
https://gist.github.com/RustyDust/2dfdd9e9d0f3b5476b5e466203123f6f

Sensors are defined as a nested Python dict that reflects the layout of 
of the output of the gist above:
`module (-> subsection (-> subsection (....))) -> key : <key definition>`

A `<key definition>` has the following elements:
  ** mandatory **
    `sensor`:         HomeAssistant's entity name for the sensor
    `friendly_name`:  HomeAssistant's description for the sensor
    `unit`:           Unit of measurement (°C, A, W, k, s ....)
    `class`:          HomeAssistant's device class for the sensor

  ** optional **
    `aka`:            List of additional entities that should be created
                      (mostly used for backward compatibility)
    `inout`:          if set to `True` two additional entities will be
                      created: 
                        an `_input` one that is set to abs(keyval) if
                        `keyval` is negative, 0 otherwiese
                        an `_output` one if `keyval` is positive, 0 otherwise
    `convert`:        Convert returned value to type ("int" or "float")
    `textmap`:        Adds another sensor postfixed with _text to the 
                      current sensor. The map needs to be specified in
                      PYTHON synatx, not JSON!
"""

SBmap = {
  "battery_system": {
    "battery_system": {
      "system": {
        "storage_capacity_per_module": {
          "sensor":         "module_capacity",
          "friendly_name":  "Battery storage per module",
          "unit":           "Wh",
          "class":          SensorDeviceClass.ENERGY,
          "convert":        int,
        },
      },
    },
    "grid_information": {
      "fac": { 
        "sensor":         "battery_system_fac",
        "friendly_name":  "Battery system - Net frequency",
        "unit":           "Hz",
        "class":          SensorDeviceClass.FREQUENCY,
        "aka":            ["state_netfrequency"],
        "convert":        float,
      },
      "ipv": {
        "sensor":         "battery_system_ipv",
        "friendly_name":  "Battery system IPV - Current",
        "unit":           "A",
        "class":          SensorDeviceClass.CURRENT,
        "convert":        float,
      },
      "ppv": {
        "sensor":         "battery_system_ppv",
        "friendly_name":  "Battery system PPV - Power",
        "unit":           "W",
        "class":          SensorDeviceClass.POWER,
        "convert":        float,
      },
      "tmax": {
        "sensor":         "battery_system_tmax",
        "friendly_name":  "Max Temperature",
        "unit":           "°C",
        "class":          SensorDeviceClass.TEMPERATURE,
        "aka":            ["tmax"],
        "convert":        float,
      },
      "upv": {
        "sensor":         "battery_system_upv",
        "friendly_name":  "Battery system UPV - Voltage",
        "unit":           "V",
        "class":          SensorDeviceClass.VOLTAGE,
        "convert":        float,
      }
    },
    "modules": {
      "sensor":         "module_count",
      "friendly_name":  "Battery module count",
      "unit":           None,
      "class":          None,
    },
  },
  "inverter": {
    "status": {
      "status": {
        "fac": {
          "sensor":         "inverter_status_fac",
          "friendly_name":  "Inverter (Status) - Net frequency",
          "unit":           "Hz",
          "class":          SensorDeviceClass.FREQUENCY,
          "aka":            ["state_netfrequency"],
          "convert":        float,
        },
      },
      "fac": {
        "sensor":         "inverter_fac",
        "friendly_name":  "Inverter - Net frequency",
        "unit":           "Hz",
        "class":          SensorDeviceClass.FREQUENCY,
        "aka":            ["state_netfrequency"],
        "convert":        float,
      },
      "ipv": {
        "sensor":         "inverter_ipv",
        "friendly_name":  "Inverter IPV - Current IPV",
        "unit":           "A",
        "class":          SensorDeviceClass.CURRENT,
        "convert":        float,
      },
      "ipv2": {
        "sensor":         "inverter_ipv2",
        "friendly_name":  "Inverter IPV - Current IPV2",
        "unit":           "A",
        "class":          SensorDeviceClass.CURRENT,
        "convert":        float,
      },
      "ppv": {
        "sensor":         "inverter_ppv",
        "friendly_name":  "Inverter PPV1 - Hybrid Solar Power PPV1",
        "unit":           "W",
        "class":          SensorDeviceClass.POWER,
        "convert":        float,
      },
      "ppv2": {
        "sensor":         "inverter_ppv2",
        "friendly_name":  "Inverter PPV2 - Hybrid Solar Power PPV2",
        "unit":           "W",
        "class":          SensorDeviceClass.POWER,
        "convert":        float,
      },
      "upv": {
        "sensor":         "inverter_upv",
        "friendly_name":  "Inverter UPV - Voltage UPV",
        "unit":           "V",
        "class":          SensorDeviceClass.VOLTAGE,
        "convert":        float,
      },
      "upv2": {
        "sensor":         "inverter_upv2",
        "friendly_name":  "Inverter UPV2 - Voltage UPV2",
        "unit":           "V",
        "class":          SensorDeviceClass.VOLTAGE,
        "convert":        float,
      },
    },
  },
  "status": {
    "Consumption_Avg": {
      "sensor":         "consumption_avg",
      "friendly_name":  "Average grid consumption",
      "unit":           "W",
      "class":          SensorDeviceClass.POWER,
    },
    "Consumption_W": {
      "sensor":         "consumption_w",
      "friendly_name":  "Current grid consumption",
      "unit":           "W",
      "class":          SensorDeviceClass.POWER,
    },
    "GridFeedIn_W": {
      "sensor":         "state_grid_inout",
      "friendly_name":  "Grid in/out power",
      "unit":           "W",
      "class":          SensorDeviceClass.POWER,
      "inout":          True,
    },
    "Production_W": {
      "sensor":         "production_w",
      "friendly_name":  "Current production",
      "unit":           "W",
      "class":          SensorDeviceClass.POWER,
      "inout":          False,
    },
    "Pac_total_W": {
      "sensor":         "state_battery_inout",
      "friendly_name":  "Battery in/out power",
      "unit":           "W",
      "class":          SensorDeviceClass.POWER,
      "inout":          True,
    },
    "RSOC": {
      "sensor":         "state_charge_real",
      "friendly_name":  "Charge percentage (real)",
      "unit":           "%",
      "class":          SensorDeviceClass.BATTERY,
    },
    "USOC": {
      "sensor":         "state_charge_user",
      "friendly_name":  "Charge percentage (user)",
      "unit":           "%",
      "class":          SensorDeviceClass.BATTERY,
    },
    "SystemStatus": {
      "sensor":         "systemstatus",
      "friendly_name":  "System Status",
      "unit":           None,
      "class":          None,
    },
    "OperatingMode": {
      "sensor":         "operating_mode",
      "friendly_name":  "Operating Mode",
      "unit":           None,
      "class":          None,
      "convert":        int,
      "textmap":        "{1:'Self Consumption', 2:'Auto', 6:'Extension module', 10:'Time of Use'}"
    }
  }
}
""" Copy/Paste template ;)
        "sensor":         "",
        "friendly_name":  "",
        "unit":           "",
        "class":          SensorDeviceClass.,
"""
