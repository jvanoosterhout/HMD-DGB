"""
This example shows a minimal end-to-end configuration of how HMD-DGB connects Home Assistant entities to physical GPIO pins using durable bindings. It shows the complete loop—from a user action in Home Assistant to a physical GPIO reaction and back.
The demo initializes HMD-DGB and configures four components:

- Home Assistant Switch
- Home Assistant Sensor
- GPIO output pin
- GPIO input pin 

The Switch has a durable binding to the GPIO output pin. This means that when the Switch is turned on in Home Assistant, the corresponding GPIO output pin is set to high.
Likewise, the GPIO input pin has a durable binding to the Sensor. When the input pin goes high, the Sensor state in Home Assistant is updated accordingly.

To run the demo, you only need to:

- Physically connect GPIO pin 20 to GPIO pin 21 on your Raspberry Pi.
- Run this script with the correct MQTT settings.
- Toggle the Switch in Home Assistant.

This closes the loop: a virtual switch triggers a physical output, which is read back as a physical input and reflected again as a virtual sensor state.

Switch → GPIO output → GPIO input → Sensor
"""
from DGB.PinMQTT import Pin_mqtt
import json
import atexit
import pkg_resources



def main():
    dgb = Pin_mqtt(name = "rpi20", broker="192.168.70.100",username="mqtt_broker", password="mqtt_broker", port=1882)
    # dgb = Pin_mqtt(name = "rpi", broker="ip-adres",username="mqtt_user", password="mqtt_pw", port=1882)
    atexit.register(dgb.__del__)
    DeviceInfo = { 
                "name": "HMD-DGB-test-device" ,
                "model": "Raspberry Pi 4",
                "manufacturer": "Raspberry Pi Holdings",
                "sw_version": pkg_resources.get_distribution("pinAPI").version,  #"""Firmware version of the device"""
                "hw_version": "RPi4" , #"""Hardware version of the device"""
                "identifiers": "rpi4_test",  #"""A list of IDs that uniquely identify the device. For example a serial number."""
                }  
    
    EntityInfo = { 
        "device": DeviceInfo ,    # """Information about the device this sensor belongs to"""
        "component": "switch", # """One of the supported MQTT components, for instance `binary_sensor`"""
        "name": "switch test",     #"""Name of the sensor inside Home Assistant"""
        "unique_id": "rpi4-switch-test" }   #"""Set this to enable editing sensor from the HA ui and to integrate with a device"""

    SwitchInfo = { "component": "switch"}

    EntityInfo_sensor = { 
        "device": DeviceInfo ,    # """Information about the device this sensor belongs to"""
        "component": "binary_sensor", # """One of the supported MQTT components, for instance `binary_sensor`"""
        "name": "sensor test",     #"""Name of the sensor inside Home Assistant"""
        "unique_id": "rpi4-sensor-test" }   #"""Set this to enable editing sensor from the HA ui and to integrate with a device"""

    SensorInfo = { "component": "binary_sensor"}

    pinoutinfo = {
        "pin": 20, #int = Field(description='GPIO pin to configure, change or read')
        "ptype": "out", # Literal[PinType.pinout.value] = Field(default= PinType.pinout.value, description='The functional type of the pin like in(put) or out(put).')
        "initial": 0, # int = Field(default= 0, description='The initial output value of the pin at the time it is created.')
        "active_state": True, #bool = Field(default= False, description='If True, when the software state is HIGH, the hardware pin is HIGH. If False, the hardware output is reversed')
        "value": 0, # int  | None = Field(default= None, description='The output value of the pin that is currently desired.')
        # "password": "ok",  #str | None = Field(default= None, description='An optional safety layer to prevent unwanted activation of a pin. ATTENTION! Do not use your daily passwords for (online) accounts as this api has no https and no encription.')
        "blink": 1 # int | None = Field(default= None, description='The blink time of the output once for this number of seconds. Note it uses the previous set value to start from, the value of this call will be ignored.')       
        }
    pinininfo = {
        "pin": 21, # int = Field(description='GPIO pin to configure, change or read')
        "ptype": "in", #  Literal[PinType.pinin.value] = Field(default= PinType.pinin.value, description='The functional type of the pin like in(put) or out(put).')
        "active_state": True, #  bool = Field(default= True, description='If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed')
        "pull_up": False, #  bool = Field(default= True, description='If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.')
        "webhook": None, #  str | None = Field(default= None, description='Endpoint in Home assistant to send state changes to at the moment they occure.')
        }
    
    binding_to_pin =  {
        "switch_test_to_pin_20": {
            "p_on": {
                "all": [{"m": { "$and": [{"unique_id": "rpi4-switch-test"},  {"payload":  "ON"}]}}],
                "run": {"action": {"unique_id": "20", "call": "on"} }
            },
            "p_off": {
                "all": [{"m": { "$and": [{"unique_id": "rpi4-switch-test"}, {"payload":  "OFF"}]}}],
                "run": {"action": {"unique_id": "20", "call": "off"} }  
            }
        }
    }
    binding_to_sensor =  {
        "pin_20_to_sensor_test": {
            "p_on": {
                "all": [{"m": { "$and": [{"unique_id": "21"},  {"payload":  1}]}}],
                "run": {"action": {"unique_id": "rpi4-sensor-test", "call": "on"} }
            },
            "p_off": {
                "all": [{"m": { "$and": [{"unique_id": "21"}, {"payload":  0}]}}],
                "run": {"action": {"unique_id": "rpi4-sensor-test", "call": "off"} }  
            }
        }
    }
       

    dgb.client.publish(topic = 'config/rpi20/devices/test',
                           payload = json.dumps({"Devices": [
                                                    {"EntityInfo" : EntityInfo | SwitchInfo},
                                                    {"EntityInfo" : EntityInfo_sensor | SensorInfo}
                                                    ],
                                                "Pins": [
                                                    {"PinInfo" : pinoutinfo},
                                                    {"PinInfo" : pinininfo}
                                                ],
                                                "Bindings" : [
                                                    {"BindInfo" : binding_to_pin},
                                                    {"BindInfo" : binding_to_sensor}

                                                ]} ))

    dgb.run()

if __name__ == "__main__":

    main()

