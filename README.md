# ha_sonnenbatterie
Homeassistant integration to show many stats of Sonnenbatterie
that should work with current versions of Sonnenbatterie.

[![Validate with hassfest](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml)
[![Validate with HACS](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/validate.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/validate.yaml)

## Installation
Easiest way to install is to add this repository via [HACS](https://hacs.xyz).

## Tested working with
* eco 8.03 9010 ND
* eco 8.0 DE 9010 ND
* sonnenBatterie 10 performance

### Won't work with older Batteries
* ex. model 9.2 eco from 2014 not working

## Sensors
The main focus of the integration is to provide a comprehensive set of sensors
for your SonnenBatterie. Right after installation the most relevant sensors 
are already activated.

> [!TIP]
> If you want to dive deeper, just head over to your Sonnenbatterie device
> settings, click on "Entities" and enable the ones you're interested in.


## Actions
Since version 2024.12.03 this integration also supports actions you can use to
set some variables that influence the behaviour of your SonnenBatterie.

Currently supported actions are:

### <a name="set_operatingmode"></a>`set_operating_mode(mode=<mode>)`
- Sets the operating mode of your SonnenBatterie.
- Supported values for `<mode>` are:
  - `"manual"`
  - `"automatic"`
  - `"timeofuse"`

##### Code snippet
``` yaml
action: sonnenbatterie.set_operating_mode
data:
  mode: "automatic"
```

##### Response
An `int` representing the mode that has been set:
- 1: `manual`
- 2: `automatic`
- 10: `timeofuse`

### `charge_battery(power=<power>)`
> [!IMPORTANT]
> Requires the SonnenBatterie to be in `manual` or `auto`mode to have any
> effect.
> 
> **Disables power delivery from the battery to local consumers!**

- Sets your battery to charge with `<power>` watts
- Disables discharging to support local consumers while charging
- Supported values for `<power>` are:
  - min. power = 0 (0 = disable functionality)
  - max. power = value of your battery's `inverter_max_power` value.
    
    The integration tries to determine the upper limit automatically
    and caps the input if a higher value than supported by the battery
    is given

##### Code snippet
``` yaml
action: sonnenbatterie.charge_battery
data:
  power: 0
```

##### Response
A `bool` value, either `True` if setting the value was successful or `False`
otherwise.

### `discharge_battery(power=<power>)`
> [!IMPORTANT]
> Requires the SonnenBatterie to be in `manual` or `auto`mode to have any
> effect.
> 
> **Enables power delivery from the battery to local consumers and may result
> in sending power to the network if local demand is lower than the value 
> given!**

- Sets your battery to discharge with `<power>` watts
- Disables charging of the battery while active
- Supported values for `<power>` are:
  - min. power = 0 (0 = disable functionality)
  - max. power = value of your battery's `inverter_max_power` value.
    
    The integration tries to determine the upper limit automatically
    and caps the input if a higher value than supported by the battery
    is given

##### Code snippet
``` yaml
action: sonnenbatterie.discharge_battery
data:
  power: 0
```

##### Response
A `bool` value, either `True` if setting the value was successful or `False`
otherwise.

### <a name="set_battery_reserve"></a>`set_battery_reserve(value=<value>)`

- Sets the percentage of energy that should be left in the battery
- `<value>` can be in the range from 0 - 100

##### Code snippet
``` yaml
action: sonnenbatterie.set_battery_reserve
data:
  value: 10
```

##### Response
An integer representing the current value of "battery reserve"

### `set_config_item(item=<item>, value=<value>)`
- Allows to set some selected configuration variables of the SonnenBattery.
- Currently supported `<item>` values:
  - "EM_OperatingMode"
    - allowed values:
      - `manual`
      - `automatic`
      - `timeofuse`
    - _prefer [`set_operating_mode`](.#set_operatingmode)) over this_
  - "EM_ToU_Schedule"
    - set a scheulde for charging in ToU mode
    - accepts JSON array as string of the format
      ``` json
      [ { "start": "10:00", 
          "stop": "11:00", 
          "threshold_p_mac": 10000
        },
        ... 
      ]
      ```
    - time ranges **must not** overlap
    - since there are only times, the schedules stay active if not deleted by
      sending an empty array (`"[]"`)
    - _prefer [`set_tou_schedule`](.#set_tou_schedule) over this_
  - "EM_USOC"
    - set the battery reserve in percent (0 - 100)
    - accepts *a string* representing the value, like `"15"` for 15% reserve
    - _prefer [`set_battery_reserve`](.#set_battery_reserve) over this_
    
##### Code snippet
``` yaml
action: sonnenbatterie.set_config_item
data:
  item: "EM_USOC"
  value: "10"
```
##### Response
``` json
{'EM_USOC': '10'}
```

### <a name="set_tou_schedule"></a>`set_tou_schedule(schedule=<schedule_array>)`

> [!IMPORTANT]
> The SonnenBatterie must be in `timeofuse` operating mode for any 
> submitted schedule to take effekt.

- Sets the shedule entries for the "Time of Use" operating mode
- The value for the schedule is a JSON array **in string format**
- The format is:
  ``` json 
  [ { "start": "10:00", 
      "stop": "11:00", 
      "threshold_p_mac": 10000
    },
    ... 
  ]
  ```
- time ranges **must not** overlap
- since there are only times, the schedules stay active if not deleted by
  sending an empty array (`"[]"`)

##### Code snippet
``` yaml
action: sonnenbatterie.set_tou_schedule_string
data:
  schedule: '[{"start":"10:00", "stop":"10:00", "threshold_p_max": 20000}]'
```

##### Result
``` json
{
  "schedule": '[{"start": "10:00", "stop": "10:00", "threshold_p_max": 20000}]'
}
```

### `get_tou_schedule()`
- Retrieves the current schedule as stored in your SonnenBatterie

##### Code snippet
``` yaml 
action: sonnenbatterie.get_tou_schedule
data: {}
```

##### Result
``` yaml
schedule: "[{\"start\":\"10:00\", \"stop\":\"10:00\", \"threshold_p_max\": 20000}]"
```

## Problems and/or unused/unavailable sensors
Depending on the software on and the operating mode of your Sonnenbatterie some
sonsors may not be available. The integration does its best to collect as many
values as possible.

If you feel that your Sonnenbatterie doesn't provide a sensor you think it 
should, you can enable a "Debug Mode" from

_Settings -> Devices & Services -> Integrations -> Sonnenbatterie -> (...) -> Reconfigure_

Then restart HomeAssistant and watch the logs.
You'll get the full data that's returned by your Sonnenbatterie there. 
Please put those logs along with the setting you want monitored into 
[a new issue](https://github.com/weltmeyer/ha_sonnenbatterie/issues).


## Screenshots :)
![image](https://user-images.githubusercontent.com/1668465/78452159-ed2d7d80-7689-11ea-9e30-3a66ecc2372a.png)
