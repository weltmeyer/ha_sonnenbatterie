# ha_sonnenbatterie
Homeassistant integration to show many stats of Sonnenbatterie
that should work with current versions of Sonnenbatterie.

[![Validate with hassfest](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml)
[![Validate with HACS](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/validate.yaml/badge.svg)](https://github.com/weltmeyer/ha_sonnenbatterie/actions/workflows/hassfest.yaml)

## Tested working with
* eco 8.03 9010 ND
* eco 8.0 DE 9010 ND
* sonnenBatterie 10 performance

## Won't work with older Batteries
* ex. model 9.2 eco from 2014 not working

## Important: ###
Set the update interval in the Integration Settings. Default is 30 seconds, don't
go below 10 seconds otherwise you might encounter an exploding recorder database.

### Problems and/or Unused/Unavailable sensors
Depending on the software on and the oparting mode of your Sonnenbatterie some
values may not be available. The integration does it's best to detect the absence
of these values. If a value isn't returned by your Sonnenbatterie you will see
entries like the following in your log:

If you feel that your Sonnenbatterie **should** provide one or more of those
you can enable the "debug_mode" from

_Settings -> Devices & Services -> Integrations -> Sonnenbatterie -> (...) -> Reconfigure_

Just enable the "Debug mode" and watch the logs of your HomeAssistant instance.
You'll get the full data that's returned by your Sonnenbatterie in the logs. 
Please put those logs along with the setting you want monitored into a new issue.

## Install
Easiest way to install is to add this repository via [HACS](https://hacs.xyz).

## Screenshots :)
![image](https://user-images.githubusercontent.com/1668465/78452159-ed2d7d80-7689-11ea-9e30-3a66ecc2372a.png)
