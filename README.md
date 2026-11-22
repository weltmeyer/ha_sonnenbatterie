[![hacs_badge][hacsbadge]][hacs] [![hainstall][hainstallbadge]][hainstall]
# ha_sonnenbatterie
Homeassistant integration to show many stats of Sonnenbatterie
that should work with current versions of Sonnenbatterie.

[![Validate with hassfest](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml)
[![Validate with HACS](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/validate.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/validate.yaml)

### Tested working with
* eco 8.03 9010 ND
* eco 8.0 DE 9010 ND
* sonnenBatterie hybrid 8.1
* sonnenBatterie 10 performance

### Won't work with older Batteries
* ex. model 9.2 eco from 2014 not working

## Installation

Requires **Home Assistant 2025.5** or newer. On older versions HACS keeps the
last release that supports them and doesn't offer newer ones.

This is an **integration**, not an app (add-on). It's installed as a custom
repository: with Home Assistant 2026.11 or newer through the built-in
**Marketplace**, on older versions through **HACS**. This button opens the
repository in either of them:

[![Open your Home Assistant instance and open this repository in the Marketplace / HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)][marketplace_repo]

### 1) via the Marketplace (Home Assistant 2026.11 or newer)
1. Go to **Settings** > **Marketplace**.
2. Select **Add from link** in the upper-right corner and enter this repository
   under **GitHub link**: `https://github.com/weltmeyer/ha_sonnenbatterie`.
   Select **Add**; if you're asked for the type, choose **Integration**.
3. Select `sonnenbatterie` in the list and install it. The latest release is
   selected automatically. Only select a different version if you've been told
   to do so by one of the maintainers.
4. Set up the integration (see [Adding or enabling the integration](#adding-or-enabling-the-integration)).
   If Home Assistant asks for a restart first (**Settings** > **System** >
   **Repairs**), restart it.

> [!NOTE]
> Already installed through HACS? Nothing to do: when you update to Home
> Assistant 2026.11, HACS content moves to the Marketplace automatically and
> keeps receiving updates.

### 2) via HACS (Home Assistant 2026.10 or older)
> [!IMPORTANT]
> You <ins>need to have [HACS](https://hacs.xyz) installed</ins>, and you need to add this
> repository as a custom **integration repository** to HACS.
1. [Add a custom **integration** repository](https://www.hacs.xyz/docs/faq/custom_repositories/) to HACS using this as the repository URL:
   `https://github.com/weltmeyer/ha_sonnenbatterie`
2. Once the repository is added, use the search bar and type `sonnenbatterie`
3. Use the 3-dot menu to the right of the list entry (not the one at the top bar!) to download/install the integration.  
   The latest release is automatically selected. Only select a different version if you've been told to do so
   by one of the maintainers.
4. After you press download and the process has completed, you have to __Restart Home Assistant__ to install the
   dependencies required by the integration
5. Setup the `sonnenbatterie` custom integration

### 3) Manual installation

1. Using your tool of choice open the directory (folder) where your HA configuration resides, e.g. where the
   `configuration.yaml` is
2. If you don't have a `custom_components` directory (folder) there, create it
3. In the `custom_components` directory (folder) create a new folder called `sonnenbatterie`
4. Download _all_ the files from the `custom_components/sonnenbatterie/` directory (folder) from this repository
5. Place the files you downloaded in the new directory (folder) `sonnenbatterie` you created
6. Restart Home Assistant
7. Setup the sonnenbatterie custom integration as described below (see [Adding or enabling the integration](#adding-or-enabling-the-integration))

## Adding or enabling the integration

> [!IMPORTANT]
> The integration must be [installed](#installation) before you can start to add or enable it!

### 1) My Home Assistant

Just click the following Button to start the configuration automatically:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)][hainstall]

### 2) Manual

- Open the Home Assistant we interface
- Go to `Configuration -> Integrations` and click the "Add Integration" button in the lower right corner
- Search for "sonnenbatterie", select the correct entry and click on it
- This starts the configuration of a new Sonnenbatterie instance. Make sure to
  - provide the correct IP address of your Sonnenbatterie within your network
  - set the update interval to a reasonable value

### Authentication

You can set up the integration in one of two ways:

- **Username and password** - the classic login, using the credentials found
  on the side of your Sonnenbatterie near the main switch.
- **API key only** - no login at all. Generate an Auth-Token in the Sonnen
  app/dashboard under _Settings -> Integrations -> Software Integration_ and
  use only that. This works for both reading and controlling the battery.

## Sensors
The main focus of the integration is to provide a comprehensive set of sensors
for your SonnenBatterie. Right after installation the most relevant sensors 
are already activated.

> [!TIP]
> If you want to dive deeper, just head over to your Sonnenbatterie device
> settings, click on "Entities" and enable the ones you're interested in.

## Energy dashboard
The integration provides the energy sensors (kWh) Home Assistant's energy
dashboard expects, so no Riemann sum (Integral) helpers are needed any more:

| Energy dashboard | Sensor |
|---|---|
| Electricity grid: Energy imported from grid | Grid import energy |
| Electricity grid: Energy exported to grid | Grid export energy |
| Solar panels: Solar production energy | meter production … kwh_imported |
| Home battery storage: Energy charged into the battery | Battery charge energy |
| Home battery storage: Energy discharged from the battery | Battery discharge energy |

Without a meter of its own, the energy dashboard calculates the home
consumption from these fields: grid import − grid export + solar production
\+ battery discharge − battery charge. So it's only correct with all five
fields set. If the home consumption always equals the solar production, the
grid and battery fields are empty or their sensors don't count.

Since Home Assistant 2026.11, the "Home consumption" section also takes a
meter that measures the whole home. On a battery with a single consumption
meter, that's usually the one: "meter consumption … kwh_imported" as "Home
energy", "Current consumption" as "Home power". It doesn't belong in any of
the fields above (e.g. solar production). Devices with their own meters (a
wallbox, a heat pump) go under "Individual electrical devices", as part of the
home consumption.

- Statistics start when a sensor is added to the dashboard; earlier values
  aren't filled in. To compare a day with the Sonnen app, compare a full day
  after the last change.
- The solar production comes from the production meter's own counter, so
  it's exact and keeps counting while Home Assistant isn't running. The
  consumption meter's counter (meter consumption … kwh_imported) is there
  as well.
- Each meter also gets a "meter … error" problem sensor (diagnostic). It
  turns on when the battery reports the meter as faulty. All of the meter's
  values and counters show as unknown meanwhile (a failed meter reports 0
  for everything), so it doesn't put a spike into the energy dashboard when
  it comes back.
- The battery has no counters for the grid and the battery itself. These
  four sensors add up the reported power over time (like the Integral helper
  with the "left" method), so they only count while Home Assistant is
  running, and short power peaks between two updates are missed. A shorter
  scan interval makes them more accurate. Short outages such as the nightly
  maintenance window are bridged with the last power read. Longer outages,
  and gaps of more than 5 minutes (or 3 scan intervals) while Home Assistant
  wasn't running, aren't counted.
- The few watts some batteries report in standby aren't counted as charging
  or discharging (unlike an Integral helper): up to 50 W only count while the
  battery also reports that it's charging or discharging.
- They start at 0. Switching the energy dashboard from your own helpers to
  these sensors starts a new history for those fields; the old one stays.
- In a cascade, these sensors are only created for the master: its values
  cover the whole cascade.

For the live power flow, the energy dashboard also takes power sensors (W).
It expects positive = from the grid / out of the battery:

| Energy dashboard | Sensor | Sign |
|---|---|---|
| Grid power | Grid in/out power, **inverted** | positive = feeding into the grid, negative = from the grid |
| Battery power | Battery charge/discharge power | positive = discharging, negative = charging |

Instead of one sensor, both fields also take two, one per direction: "Grid
in power" (from the grid) and "Grid out power" (into the grid), "Battery
discharge power" and "Battery charge power". These four are disabled by
default.

## Cascades
In a cascade, several batteries act as one system: the master has the meters
and controls the cascade, the slaves only report their own unit.

- Set up the integration for the **master**. Its sensors cover the whole
  cascade (consumption, production, grid, installed capacity, max. power),
  and the diagnostic sensor "Cascade members" shows the number of units,
  with their serial numbers and status as attributes. The battery reports
  its state of charge (relative), full charge capacity and battery power for
  the whole cascade on the master, so the master's sensors for these show
  the cascade, not the master unit alone. The master's battery details
  (cycles, temperatures, cell voltages) are its own.
- The master's slaves then show up as discovered devices. Add them to see
  each unit's own values (state of charge, battery power, cycles,
  temperatures, capacity). The master's username and password are suggested;
  each attempt is one login, and failed logins make the battery block further
  ones for a while. A slave's IP address is updated automatically when the
  master reports a new one.
- Slaves are read-only: no controls (setpoints, operating mode, buttons) and
  no actions, as the master controls the cascade. Their consumption,
  production, grid, power meter and cascade-wide settings sensors are left
  out, since a slave has no meters. If a slave was added before this version,
  those entities are removed from it.


## Actions
Since version 2025.01.01 this integration also supports actions you can use to
set some variables that influence the behaviour of your SonnenBatterie.

> [!NOTE]
> All actions require you ro provide a `device_id` to correctly identify the
> Sonnenbatterie you want to talk to. To find the device id for your Sonnenbatterie
> use the developer tools provided by Home Assistant. Just open the "Actions" tab
> and select an action an a device. Then switch to YAML mode where instead of the
> user-friendly name the device id will be displayed.

Currently supported actions are:

### <a name="set_operatingmode"></a>`set_operating_mode(mode=<mode>)`
- Sets the operating mode of your SonnenBatterie.
- Supported values for `<mode>` are:
  - `"manual"`
  - `"automatic"`
  - `"timeofuse"`
  - `"optimizing"`

> [!NOTE]
> Whether a mode can be set is decided by the battery, and a refused mode
> ends with an error message. According to sonnen, `timeofuse` isn't
> available in France, `automatic` shouldn't be used on sonnenBatterie 10
> Hybrid systems, and no mode can be changed while a virtual power plant
> (VPP) is active. `optimizing` needs a recent firmware: it was refused on
> 1.30.x and works on 1.40.5. The same applies to `set_operating_mode_num`
> and the "Operating mode" select.

##### Code snippet
``` yaml
action: sonnenbatterie.set_operating_mode
data:
  device_id: "<your sb instance's device id>"
  mode: "automatic"
```

##### Response
The name of the mode that has been set:
- `manual`
- `automatic`
- `timeofuse`
- `optimizing`

### <a name="set_operatingmode_num"></a>`set_operating_mode_num(mode=<mode>)`
- Sets the operating mode of your SonnenBatterie.
- Supported values for `<mode>` are:
  - `1`
  - `2`
  - `10`
  - `11`

##### Code snippet
``` yaml
action: sonnenbatterie.set_operating_mode_num
data:
  device_id: "<your sb instance's device id>"
  mode: 2
```

##### Response
An `int` representing the mode that has been set:
- 1: `manual`
- 2: `automatic`
- 10: `timeofuse`
- 11: `optimizing`

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
  device_id: "<your sb instance's device id>"
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
  device_id: "<your sb instance's device id>"
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
  device_id: "<your sb instance's device id>"
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
      - `optimizing`
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
  device_id: "<your sb instance's device id>"
  item: "EM_USOC"
  value: "10"
```
##### Response
``` json
{"EM_USOC": "10"}
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
  device_id: "<your sb instance's device id>"
  schedule: '[{"start":"10:00", "stop":"10:00", "threshold_p_max": 20000}]'
```

##### Result
``` json
{
  "schedule": [{"start": "10:00", "stop": "10:00", "threshold_p_max": 20000}]
}
```

### `get_tou_schedule()`
- Retrieves the current schedule as stored in your SonnenBatterie

##### Code snippet
``` yaml 
action: sonnenbatterie.get_tou_schedule
data:
  deviceid: "<your sb instance's device id>"
```

##### Result
``` json
{
  "schedule": [{"start": "10:00", "stop": "10:00", "threshold_p_max": 20000}]
}
```

### <a name="get_operatingmode"></a>`get_operating_mode()`
- Retrieves the current operating mode of your SonnenBatterie.

##### Code snippet
``` yaml
action: sonnenbatterie.get_operating_mode
data:
  device_id: "<your sb instance's device id>"
```

##### Response
The name of the mode that has been set:
- `manual`
- `automatic`
- `timeofuse`
- `optimizing`

### <a name="get_operatingmode_num"></a>`get_operating_mode_num()`
- Retrieves the current operating mode of your SonnenBatterie in numeric form

##### Code snippet
``` yaml
action: sonnenbatterie.get_operating_mode_num
data:
  device_id: "<your sb instance's device id>"
```

##### Response
An `int` representing the mode that has been set:
- 1: `manual`
- 2: `automatic`
- 10: `timeofuse`
- 11: `optimizing`

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

## Development
The tests run a real Home Assistant core against simulated batteries
(`tests/fake_battery.py`), built from real sb_info reports with all serial
numbers and other identifiers replaced (`tests/fixtures`). They also run on
GitHub for every push and pull request.

```shell
python3 -m pip install -r requirements.txt -r requirements_test.txt
python3 -m pytest
```

The dev container (`.devcontainer`, for VS Code and Zed) installs both.

GitHub runs them on two Home Assistant versions: the one in `requirements.txt`
and the minimum in `hacs.json` (`requirements_test_min.txt`, Python 3.13).

---
[hacs]: https://hacs.xyz
[marketplace_repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=weltmeyer&repository=ha_sonnenbatterie&category=integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=ccc

[hainstall]: https://my.home-assistant.io/redirect/config_flow_start/?domain=sonnenbatterie
[hainstallbadge]: https://img.shields.io/badge/dynamic/json?style=for-the-badge&logo=home-assistant&logoColor=ccc&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.sonnenbatterie.total
