#!/usr/bin/env python
# encoding: utf-8
"""
Device keeper to manage home assistant device and entity configurations.

Jeroen van Oosterhout, 24-12-2025
"""

import logging
import time
from ha_mqtt_discoverable import Settings, DeviceInfo, sensors
import json
from paho.mqtt.client import Client, MQTTMessage
from durable.lang import post
from PinAPI.DataStore import DataStore

logging.basicConfig(level='INFO')   

class DeviceKeeper(object):
    def __init__(self, mqtt_settings:Settings, datastore:DataStore):
        self.entities = []
        self.mqtt_settings = mqtt_settings
        self.datastore = datastore

        # self.switches:list[sensors.Switch] = []
        # self.switches_dict:dict[str, any] = {}
        # self.binarysensor_dict:dict[str, any] = {}
        # self.callable_dict : dict[str, list[callable]] = {} # { "unique_id: [device.on, device.off]"}
        self.logger = logging.getLogger("DeviceKeeper")
        self.logger.info('starting Entitykeeper')
    
    def new_device(self, payload):
        # print(payload)
        for dev in payload: 
            if "EntityInfo" in dev:
                if "component" in dev['EntityInfo']:
                    if dev['EntityInfo']['component'] == "cover":
                        self.configure_cover(dev)
                    elif dev['EntityInfo']['component'] == "sensor":
                        self.configure_sensor(dev)
                    elif dev['EntityInfo']['component'] == "switch":
                        self.configure_switch(dev)
                    elif dev['EntityInfo']['component'] == "light":
                        self.configure_light(dev)
                    elif dev['EntityInfo']['component'] == "button":
                        self.configure_button(dev)
                    elif dev['EntityInfo']['component'] == "text":
                        self.configure_text(dev)
                    elif dev['EntityInfo']['component'] == "number":
                        self.configure_number(dev)
                    elif dev['EntityInfo']['component'] == "select":
                        self.configure_select(dev)
                    elif dev['EntityInfo']['component'] == "binary_sensor":
                        self.configure_binary_sensor(dev)
                    else:
                        self.logger.warning("Unknown component '{}', skipping this configuration".format(dev['EntityInfo']['component'])) 
                else:
                    self.logger.warning("No component in EntityInfo, skipping this configuration {}".format(dev['EntityInfo'])) 
            else:
                self.logger.warning("No EntityInfo in payload, skipping this configuration") 

    def configure_cover(self, payload):
        self.logger.info("creating cover")
        time_based_state = False
        password_check = False

        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("cover has time_based_state, adding to settings")
            time_based_state = True
            time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        if "password" in payload["EntityInfo"]:
            self.logger.info("cover has password, adding to settings")
            password_check = True
            password = payload["EntityInfo"]["password"]
            del payload["EntityInfo"]["password"]

        cover_info = sensors.CoverInfo(**payload["EntityInfo"])
        
        def my_callback(client: Client, user_data, message: MQTTMessage):
            payload = message.payload.decode()
            self.logger.info("turn cover {}: {}".format(device._entity.unique_id, payload))
            
            for rulset_name in self.datastore.get_bindings(device._entity.unique_id):
                self.logger.info("posting event to ruleset {}: {}".format(rulset_name, payload))    
                post(rulset_name, {"value": payload.lower()})

            if payload == "OPEN":
                device.opening()
                device.open()
                self.logger.info("ik open")
            elif payload == "CLOSE":
                device.closing()
                device.closed()
                self.logger.info("ik sluit")
            elif payload == "STOP":
                device.stopped()
                self.logger.info("ik stop")

        device = sensors.Cover(Settings(mqtt=self.mqtt_settings, entity=cover_info), my_callback)
        self.datastore.add_device(device._entity.unique_id, device, {"open": device.open, 
                                                                     "closed": device.closed, 
                                                                     "stopped": device.stopped, 
                                                                     "opening": device.opening, 
                                                                     "closing": device.closing})
        device.closed()
        self.logger.info("Cover '{}' with unique_id '{}' made and closed.".format(device._entity.name, device._entity.unique_id))   

    def configure_sensor(self, payload):
        pass

    def configure_switch(self, payload):
        self.logger.info("creating switch")
        switch_info = sensors.SwitchInfo(**payload["EntityInfo"])

        def my_callback(client: Client, user_data, message: MQTTMessage):
            payload = message.payload.decode()
            self.logger.info("turn switch {}: {}".format(device._entity.unique_id, payload))
            
            for rulset_name in self.datastore.get_bindings(device._entity.unique_id):
                self.logger.info("posting event to ruleset {}: {}".format(rulset_name, payload))    
                post(rulset_name, {"value": payload.lower()})

            if payload == "ON":
                # turn_my_custom_thing_on()
                # Let HA know that the switch was successfully activated
                device.on()
            elif payload == "OFF":
                # turn_my_custom_thing_off()
                # Let HA know that the switch was successfully deactivated
                device.off()

        device = sensors.Switch(Settings(mqtt=self.mqtt_settings, entity=switch_info), my_callback)
        # switch.
        self.datastore.add_device(device._entity.unique_id, device, {"on": device.on, "off": device.off})

        device.off()
        
        self.logger.info("Switch '{}' with unique_id '{}' made and deactivated.".format(device._entity.name, device._entity.unique_id))
        # self.switches[-1].mqtt_client.message_callback_add(self.switches[-1]._command_topic, my_callback)
        
        # self.mqtt_client.message_callback_add(self._command_topic, my_callback)
    
    def configure_light(self, payload):
        pass
    
    def configure_button(self, payload):
        pass
    
    def configure_text(self, payload):
        pass
    
    def configure_number(self, payload):
        pass
    
    def configure_select(self, payload):
        pass
    
    def configure_binary_sensor(self, payload):
        
        self.logger.info("creating binary sensor")
        binarysensor_info = sensors.BinarySensorInfo(**payload["EntityInfo"])
        device = sensors.BinarySensor(Settings(mqtt=self.mqtt_settings, entity=binarysensor_info))

        self.datastore.add_device(device._entity.unique_id, device, {"on": device.on, "off": device.off})
        self.logger.info("Binary sensor '{}' with unique_id '{}' made and deactivated.".format(device._entity.name, device._entity.unique_id))
        device.off()

