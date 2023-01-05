import traceback
from datetime import datetime
import sys
# pylint: disable=unused-wildcard-import
from .const import *
# pylint: enable=unused-wildcard-import
import threading
import time
from homeassistant.helpers import config_validation as cv

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass
)

# pylint: disable=no-name-in-module
from sonnenbatterie import sonnenbatterie
# pylint: enable=no-name-in-module

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_IP_ADDRESS,
    EVENT_HOMEASSISTANT_STOP,
    CONF_SCAN_INTERVAL,
)

async def async_setup_entry(hass, config_entry,async_add_entities):
    """Set up the sensor platform."""
    LOGGER.info('SETUP_ENTRY')
    username=config_entry.data.get(CONF_USERNAME)
    password=config_entry.data.get(CONF_PASSWORD)
    ipaddress=config_entry.data.get(CONF_IP_ADDRESS)
    updateIntervalSeconds=config_entry.options.get(CONF_SCAN_INTERVAL)
    def _internal_setup(_username,_password,_ipaddress):
        return sonnenbatterie(_username,_password,_ipaddress)
    sonnenInst=await hass.async_add_executor_job(_internal_setup,username,password,ipaddress);
    systemdata=await hass.async_add_executor_job(sonnenInst.get_systemdata);
    serial=systemdata["DE_Ticket_Number"]
    LOGGER.info("{0} - INTERVAL: {1}".format(DOMAIN,updateIntervalSeconds))

    sensor = SonnenBatterieSensor(id="sensor.{0}_{1}".format(DOMAIN,serial))
    async_add_entities([sensor])

    monitor = SonnenBatterieMonitor(hass,sonnenInst, sensor, async_add_entities,updateIntervalSeconds)
    hass.data[DOMAIN][config_entry.entry_id]={"monitor":monitor}
    monitor.start()

    def _stop_monitor(_event):
        monitor.stopped=True

    #hass.states.async_set
    hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, _stop_monitor)
    LOGGER.info('Init done')
    return True


class SonnenBatterieSensor(SensorEntity):
    def __init__(self,id,name=None):
        self._attributes = {}
        self._state ="NOTRUN"
        self.entity_id=id
        if name is None:
            name=id
        self._name=name
        LOGGER.info("Create Sensor {0}".format(id))

    def set_state(self, state):
        """Set the state."""
        if self._state==state:
            return
        self._state = state
        try:
            self.schedule_update_ha_state()
        except:
            LOGGER.error("Failing sensor: "+self.name)
            #raise

    def set_attributes(self, attributes):
        """Set the state attributes."""
        self._attributes = attributes

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return self.entity_id

    @property
    def should_poll(self):
        """Only poll to update phonebook, if defined."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    def update(self):
        LOGGER.info("update "+self.entity_id)
        """Update the phonebook if it is defined."""
        #self.powermeter=self._sbInst.getpowermeter()
        #self.state=self.powermeter[0]['v_l1_l2']

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._attributes.get("unit_of_measurement",None)

    @property
    def device_class(self):
        """Return the device_class."""
        return self._attributes.get("device_class",None)

    @property
    def state_class(self):
        """Return the unit of measurement."""
        return self._attributes.get("state_class",None)


class SonnenBatterieMonitor:
    def __init__(self,hass, sbInst, sensor,async_add_entities,updateIntervalSeconds):
        self.hass=hass;
        self.latestData={}
        self.disabledSensors=[""]
        #self.IsHybrid=False;
        self.MinimumKeepBatteryPowerPecentage=7.0#is this valid for all batteries? 7% Eigenbehalt?
        self.NormalBatteryVoltage=50.0#real? dunno

        self.stopped = False
        self.sensor=sensor
        self.sbInst: sonnenbatterie = sbInst
        self.meterSensors={}
        self.updateIntervalSeconds=updateIntervalSeconds
        self.async_add_entities=async_add_entities
        #self.setupEntities()

    def start(self):
        threading.Thread(target=self.watcher).start()

    def updateData(self):
        try:##ignore errors here, may be transient
            self.latestData["powermeter"]=self.sbInst.get_powermeter()
            self.latestData["battery_system"]=self.sbInst.get_batterysystem()
            self.latestData["inverter"]=self.sbInst.get_inverter()
            self.latestData["systemdata"]=self.sbInst.get_systemdata()
            self.latestData["status"]=self.sbInst.get_status()
            self.latestData["battery"]=self.sbInst.get_battery()
        except:
            e = traceback.format_exc()
            LOGGER.error(e)
            return

        """ some batteries seem to have status in status key instead directly in status... """
        if not "state_netfrequency" in self.disabledSensors:
            try:
                if not 'fac' in self.latestData["inverter"]['status']:
                    # try to find frequency in battery_system/grid_information
                    if 'fac' in self.latestData["battery_system"]["grid_information"]:
                        self.latestData['inverter']['status']['fac'] = self.latestData['battery_system']['grid_information']['fac']
                    else:
                        self.latestData["inverter"]['status']=self.latestData["inverter"]['status']['status']
            except:
                self.disabledSensors.append("state_netfrequency")
                e = traceback.format_exc()
                LOGGER.error(e)
                LOGGER.error("inverter JSON For Developer in next message")
                LOGGER.error(self.latestData["inverter"])

    def setupEntities(self):
        self.updateData();
        self.AddOrUpdateEntities()

    def watcher(self):
        LOGGER.info('Start Watcher Thread:')

        while not self.stopped:
            try:
                #LOGGER.warning('Get PowerMeters: ')
                self.updateData();
                self.parse()

                statedisplay="standby"
                if self.latestData["status"]["BatteryCharging"]:
                    statedisplay="charging"
                elif self.latestData["status"]["BatteryDischarging"]:
                    statedisplay="discharging"

                self.sensor.set_state(statedisplay)
                self.AddOrUpdateEntities()
                self.sensor.set_attributes(self.latestData["systemdata"])
            except:
                e = traceback.format_exc()
                LOGGER.error(e)
            if self.updateIntervalSeconds is None:
                self.updateIntervalSeconds=10

            time.sleep(max(1,self.updateIntervalSeconds))

    def parse(self):
        meters= self.latestData["powermeter"]
        battery_system=self.latestData["battery_system"]
        #inverter=self.latestData["inverter"]
        #systemdata=self.latestData["systemdata"]
        #status=self.latestData["status"]
        #battery=self.latestData["battery"]

        attr={}
        for meter in meters:
            prefix="{0}_{1}_{2}-".format( meter['direction'],meter['deviceid'],meter['channel'])
            for name in meter:
                parmName=prefix+name
                attr[parmName]=meter[name]

        bat_sys_dict=flattenObj("battery_system","-",battery_system)
        attr.update(bat_sys_dict)
        """
        modelname="undefined??";
        try:
            modelname=battery_system["battery_system"]["system"]["model_name"]
            if "ybrid" in modelname:
                self.IsHybrid=True
                LOGGER.warning("Found Hybrid Sonnenbatterie"+"("+modelname+")")
            else:
                self.IsHybrid=False
                LOGGER.warning("Found Non-Hybrid Sonnenbatterie"+"("+modelname+")")

        except:
            LOGGER.error("Failing detection for IsHybrid."("+modelname+")")
        """
        #self.sensor.set_attributes(attr)

    def _AddOrUpdateEntity(self,id,friendlyname,value,unit,device_class):
        if id in self.meterSensors:
            sensor=self.meterSensors[id]
            #sensor.set_attributes({"unit_of_measurement":unit,"device_class":"power","friendly_name":friendlyname})
            sensor.set_state(value)
        else:
            sensor=SonnenBatterieSensor(id,friendlyname)
            sensor.set_attributes({"unit_of_measurement":unit,"device_class":device_class,"friendly_name":friendlyname,"state_class":"measurement"})
            self.async_add_entities([sensor])
            self.meterSensors[id]=sensor

    def AddOrUpdateEntities(self):
        meters= self.latestData["powermeter"]
        battery_system=self.latestData["battery_system"]
        inverter=self.latestData["inverter"]
        systemdata=self.latestData["systemdata"]
        status=self.latestData["status"]
        battery=self.latestData["battery"]

        """systemdata defines the serialnumber of the battery"""
        serial=systemdata["DE_Ticket_Number"]
        allSensorsPrefix="sensor."+DOMAIN+"_"+serial+"_"

        """this and that from the states"""
        if not "state_netfrequency" in self.disabledSensors:
            # try:
            if 'fac' in inverter['status']:
                val=inverter['status']['fac']
                sensorname=allSensorsPrefix+"state_netfrequency"
                unitname="Hz"
                friendlyname="Net Frequency"
                device_class= SensorDeviceClass.FREQUENCY #"frequency"
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            # except:
            else:
                self.disabledSensors.append("state_netfrequency")
                # e = traceback.format_exc()
                # LOGGER.error(e)
                LOGGER.error("No 'fac' in inverter")
                LOGGER.error(inverter)

        if not "inverter_ppv" in self.disabledSensors:
            # try:
            if 'ppv' in inverter['status']:
                val=inverter['status']['ppv']
                sensorname=allSensorsPrefix+"inverter_ppv"
                unitname="W"
                friendlyname="Inverter PPV1 - Hybrid Solar Power PPV1"
                device_class=SensorDeviceClass.POWER#"power"
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            # except:
            elif 'ppv' in battery_system['grid_information']:
                val=battery_system['grid_information']['ppv']
                sensorname=allSensorsPrefix+"inverter_ppv"
                unitname="W"
                friendlyname="Inverter PPV1 - Hybrid Solar Power PPV1"
                device_class=SensorDeviceClass.POWER#"power"
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            else:
                self.disabledSensors.append("inverter_ppv")
                # e = traceback.format_exc()
                # LOGGER.error(e)
                LOGGER.error("No 'ppv' in inverter")
                LOGGER.error(inverter)

        if not "inverter_ppv2" in self.disabledSensors:
            # try:
            if 'ppv2' in inverter['status']:
                val=inverter['status']['ppv2']
                sensorname=allSensorsPrefix+"inverter_ppv2"
                unitname="W"
                friendlyname="Inverter PPV2 - Hybrid Solar Power PPV2"
                device_class=SensorDeviceClass.POWER#"power"
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            elif 'ppv2' in battery_system['grid_information']:
                val=battery_system['grid_information']['ppv2']
                sensorname=allSensorsPrefix+"inverter_ppv"
                unitname="W"
                friendlyname="Inverter PPV2 - Hybrid Solar Power PPV2"
                device_class=SensorDeviceClass.POWER#"power"
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            # except:
            else:
                self.disabledSensors.append("inverter_ppv2")
                # e = traceback.format_exc()
                # LOGGER.error(e)
                LOGGER.error("NO 'ppv2' in interverter")
                LOGGER.error(inverter)

        if not "inverter_ipv" in self.disabledSensors:
            try:
                LOGGER.error("inverter JSON For Developer in next message")
                LOGGER.error(inverter)
                val=inverter['status']['ipv']
                sensorname=allSensorsPrefix+"inverter_ipv"
                unitname="A"
                friendlyname="Inverter IPV - Current IPV"
                device_class=SensorDeviceClass.CURRENT
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            except:
                self.disabledSensors.append("inverter_ipv")
                e = traceback.format_exc()
                LOGGER.error(e)
                LOGGER.error(inverter)

        if not "inverter_ipv2" in self.disabledSensors:
            try:
                LOGGER.error("inverter JSON For Developer in next message")
                LOGGER.error(inverter)
                val=inverter['status']['ipv2']
                sensorname=allSensorsPrefix+"inverter_ipv2"
                unitname="A"
                friendlyname="Inverter IPV - Current IPV2"
                device_class=SensorDeviceClass.CURRENT
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            except:
                self.disabledSensors.append("inverter_ipv2")
                e = traceback.format_exc()
                LOGGER.error(e)
                LOGGER.error(inverter)

        if not "inverter_upv" in self.disabledSensors:
            try:
                LOGGER.error("inverter JSON For Developer in next message")
                LOGGER.error(inverter)
                val=inverter['status']['upv']
                sensorname=allSensorsPrefix+"inverter_upv"
                unitname="V"
                friendlyname="Inverter IPV - Voltage UPV"
                device_class=SensorDeviceClass.VOLTAGE
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            except:
                self.disabledSensors.append("inverter_upv")
                e = traceback.format_exc()
                LOGGER.error(e)
                LOGGER.error(inverter)

        if not "inverter_upv2" in self.disabledSensors:
            try:
                LOGGER.error("inverter JSON For Developer in next message")
                LOGGER.error(inverter)
                val=inverter['status']['upv2']
                sensorname=allSensorsPrefix+"inverter_upv2"
                unitname="V"
                friendlyname="Inverter IPV - Voltage UPV2"
                device_class=SensorDeviceClass.VOLTAGE
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
            except:
                self.disabledSensors.append("inverter_upv2")
                e = traceback.format_exc()
                LOGGER.error(e)
                LOGGER.error(inverter)


        """whatever comes next"""
        val_modulecount=int(battery_system['modules'])
        sensorname=allSensorsPrefix+"module_count"
        unitname=""
        friendlyname="Battery module count"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_modulecount,unitname,SensorDeviceClass.BATTERY)

        if not "tmax" in self.disabledSensors:
            # try:
            if "tmax" in battery_system['grid_information']:
                val_tmax=float(battery_system['grid_information']['tmax'])
                sensorname=allSensorsPrefix+"tmax"
                unitname="°C"
                friendlyname="Max Temperature"
                self._AddOrUpdateEntity(sensorname,friendlyname,val_tmax,unitname,SensorDeviceClass.TEMPERATURE)
            # except:
            else:
                self.disabledSensors.append("tmax")
                # e = traceback.format_exc()
                # LOGGER.error(e)
                LOGGER.error("No 'tmax' in grid_information")
                LOGGER.error(battery_system)

        val_module_capacity=int(battery_system['battery_system']['system']['storage_capacity_per_module'])
        sensorname=allSensorsPrefix+"module_capacity"
        unitname="Wh"
        friendlyname="Battery storage_capacity_per_module"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_module_capacity,unitname,SensorDeviceClass.ENERGY)

        total_installed_capacity=int(val_modulecount*val_module_capacity)

        """grid input/output"""
        val=status['GridFeedIn_W']
        val_in=0
        val_out=0
        if val>=0:
            val_out=val
        else:
            val_in=abs(val)

        sensorname=allSensorsPrefix+"state_grid_input"
        unitname="W"
        friendlyname="Grid Input Power (buy)"

        self._AddOrUpdateEntity(sensorname,friendlyname,val_in,unitname,SensorDeviceClass.POWER)

        sensorname=allSensorsPrefix+"state_grid_output"
        unitname="W"
        friendlyname="Grid Output Power (sell)"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_out,unitname,SensorDeviceClass.POWER)

        sensorname=allSensorsPrefix+"state_grid_inout"
        unitname="W"
        friendlyname="Grid In/Out Power"
        self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,SensorDeviceClass.POWER)

        """battery states"""
        """battery load percent"""
        val=status['USOC']
        sensorname=allSensorsPrefix+"state_charge_user"
        unitname="%"
        friendlyname="Charge Percentage User"
        self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,SensorDeviceClass.BATTERY)

        val_rsoc=float(status['RSOC'])
        sensorname=allSensorsPrefix+"state_charge_real"
        unitname="%"
        friendlyname="Charge Percentage Real"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_rsoc,unitname,SensorDeviceClass.BATTERY)

        """battery input/output"""
        val=status['Pac_total_W']
        val_in=0
        val_out=0
        if val>=0:
            val_out=val
        else:
            val_in=abs(val)
        sensorname=allSensorsPrefix+"state_battery_input"
        unitname="W"
        friendlyname="Battery Charging Power"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_in,unitname,SensorDeviceClass.POWER)

        sensorname=allSensorsPrefix+"state_battery_output"
        unitname="W"
        friendlyname="Battery Discharging Power"
        self._AddOrUpdateEntity(sensorname,friendlyname,val_out,unitname,SensorDeviceClass.POWER)

        sensorname=allSensorsPrefix+"state_battery_inout"
        unitname="W"
        friendlyname="Battery In/Out Power"
        self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,SensorDeviceClass.POWER)

        """ gross consumption """
        if 'Consumption_W' in status:
            val = status['Consumption_W']
            sensorname = allSensorsPrefix+'consumption_w'
            unitname = "W"
            friendlyname = "Current grid consumption"
            self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,SensorDeviceClass.POWER)

        """" average consumption """
        if 'Consumption_Avg' in status:
            val = status['Consumption_Avg']
            sensorname = allSensorsPrefix+'consumption_avg'
            unitname = "W"
            friendlyname = "Average grid consumption"
            self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,SensorDeviceClass.POWER)

        """" Battery Raw Capacity Calc """
        measurements_status=battery['measurements']['battery_status']
        #val_fullchargecapacity=float(measurements_status['fullchargecapacity']) #Ah
        #val_remainingcapacity=float(measurements_status['remainingcapacity']) #Ah
        #val_systemdcvoltage=float(measurements_status['systemdcvoltage']) #V, dont use this atm, use self.NormalBatteryVoltage=50.0

        #calc_totalcapacity=self.NormalBatteryVoltage*val_fullchargecapacity#Wh #total_installed_capacity
        #calc_resrtictedcapacity=calc_totalcapacity*(self.MinimumKeepBatteryPowerPecentage/100)
        calc_resrtictedcapacity=total_installed_capacity*(self.MinimumKeepBatteryPowerPecentage/100)

        #calc_remainingcapacity=self.NormalBatteryVoltage*val_remainingcapacity#Wh, real value => pecentage is RSOC
        #calc_remainingcapacity_usable=calc_remainingcapacity-calc_resrtictedcapacity#Wh, usable capacity
        calc_remainingcapacity=total_installed_capacity*(val_rsoc/100.0)#Wh, real value => pecentage is RSOC
        calc_remainingcapacity_usable=calc_remainingcapacity-calc_resrtictedcapacity#Wh, usable capacity

        sensorname=allSensorsPrefix+"state_total_capacity_real"
        unitname="Wh"
        friendlyname="Total Capacity Real"
        self._AddOrUpdateEntity(sensorname,friendlyname,int(total_installed_capacity),unitname,SensorDeviceClass.ENERGY)

        sensorname=allSensorsPrefix+"state_total_capacity_usable"
        unitname="Wh"
        friendlyname="Total Capacity Usable"
        self._AddOrUpdateEntity(sensorname,friendlyname,int(total_installed_capacity-calc_resrtictedcapacity),unitname,SensorDeviceClass.ENERGY)

        sensorname=allSensorsPrefix+"state_remaining_capacity_real"
        unitname="Wh"
        friendlyname="Remaining Capacity Real"
        self._AddOrUpdateEntity(sensorname,friendlyname,int(calc_remainingcapacity),unitname,SensorDeviceClass.ENERGY)

        sensorname=allSensorsPrefix+"state_remaining_capacity_usable"
        unitname="Wh"
        friendlyname="Remaining Capacity Usable"
        self._AddOrUpdateEntity(sensorname,friendlyname,int(calc_remainingcapacity_usable),unitname,SensorDeviceClass.ENERGY)

        """end battery states"""

        """powermeter values"""
        for meter in meters:
            sensornamePrefix=allSensorsPrefix+"meter_"+("{0}_{1}_{2}".format( meter['direction'],meter['deviceid'],meter['channel']))
            sensornamePrefix=sensornamePrefix.lower()
            generateSensorsFor={"w_l1","w_l2","w_l3","v_l1_n","v_l2_n","v_l3_n","v_l1_l2","v_l2_l3","v_l3_l1","w_total","a_l1","a_l2","a_l3"}

            for sensormeter in generateSensorsFor:
                sensorname=sensornamePrefix+"_"+sensormeter
                val=meter[sensormeter]
                val=round(val,2)
                unitname=(sensormeter[0]+"").upper()
                device_class=SensorDeviceClass.POWER
                if(unitname=="V"):
                    device_class=SensorDeviceClass.VOLTAGE
                elif unitname=="A":
                    device_class=SensorDeviceClass.CURRENT
                friendlyname="{0} {1}".format(meter['direction'],sensormeter)
                self._AddOrUpdateEntity(sensorname,friendlyname,val,unitname,device_class)
