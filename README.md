# ha_sonnenbatterie
Homeassistant integration to show many stats of Sonnenbatterie

Should work with current versions of Sonnenbatterie.

[![Validate with hassfest](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml)

## Tested working with
* eco 8.03 9010 ND
* eco 8.0 DE 9010 ND
* sonnenBatterie 10 performance

## Wont work with older Batteries
* ex. model 9.2 eco from 2014 not working

## Important: ###
Set the update interval in the Integration Settings. Default is 10 seconds, which may kill your recorder database

### Unused/Unavailable sensors
Depending on the software on and the oparting mode of your Sonnenbatterie some
values may not be available. The integration does it's best to detect the absence
of these values. If a value isn't returned by your Sonnenbatterie you will see
entries like the following in your log:

```
… WARNING (Thread-1 (watcher)) [custom_components.sonnenbatterie] No 'ppv2' in inverter -> sensor disabled
… WARNING (Thread-1 (watcher)) [custom_components.sonnenbatterie] No 'ipv' in inverter -> sensor disabled
… WARNING (Thread-1 (watcher)) [custom_components.sonnenbatterie] No 'ipv2' in inverter -> sensor disabled
… WARNING (Thread-1 (watcher)) [custom_components.sonnenbatterie] No 'upv' in inverter -> sensor disabled
… WARNING (Thread-1 (watcher)) [custom_components.sonnenbatterie] No 'upv2' in inverter -> sensor disabled
```

Those aren't errors! There's nothing to worry about. This just tells you that
your Sonnenbatterie doesn't provide these values.

If you feel that your Sonnenbatterie **should** provide one or more of those
you can enable the "debug_mode" from

_Settings -> Devices & Services -> Integrations -> Sonnenbatterie_

Just enable the "Debug mode" and restart your HomeAssistant instance. You'll get
the full data that's returned by your Sonnenbatterie in the logs. Please put those
logs along with the setting you want monitored into a new issue.

## Install
Easiest way is to add this repository to hacs.


## Screenshots :)
![image](https://user-images.githubusercontent.com/1668465/78452159-ed2d7d80-7689-11ea-9e30-3a66ecc2372a.png)
