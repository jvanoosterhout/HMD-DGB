#!/usr/bin/env python
# encoding: utf-8
"""
Device keeper to manage home assistant device and entity configurations.

Jeroen van Oosterhout, 24-12-2025
"""

from typing import Optional, Union
import logging
import time
import psutil
from gpiozero import CPUTemperature
from PinAPI.PinKeeper import PinKeeper
from PinAPI.PinModels import *
from PinAPI.PinModels import *
from ha_mqtt_discoverable import Settings, DeviceInfo, sensors
import json
from paho.mqtt.client import Client, MQTTMessage

logging.basicConfig(level='INFO')

class DeviceKeeper(object):
    def __init__(self, mqtt_settings):
        self.entities = []
        self.mqtt_settings = mqtt_settings
        self.pin_keeper = PinKeeper()

        self.switches:list[sensors.Switch] = []
        self.logger = logging.getLogger("Entitykeeper")
        self.logger.info('starting Entitykeeper')
    
    def new_device(self, payload):
        print(payload)
        if "Devices" in payload: 
            for dev in payload['Devices']: 
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
                elif "pininfo" in dev:
                    try:
                        pin_model = PinModel(dev["pininfo"])
                    except ValidationError as e: # Exception as e
                        raise self.logger.warning(str(e))
                    
                    self.logger.info('Posting new (value for) pin: {}'.format(pin_model))
                    if self.pin_keeper.SetPin(pin_model): 
                        self.logger.info("pin made succesfully")
                    else:
                        self.logger.info("total failure")
                
                else:
                    self.logger.warning("No EntityInfo in payload, skipping this configuration") 


    def configure_cover(self, payload):
        pass
    
    def configure_sensor(self, payload):
        pass

    def configure_switch(self, payload):
        self.logger.info("creating switch")
        if "SwitchInfo" in payload:
            self.logger.info("SwitchInfo of switch found")
            merged_json = payload["EntityInfo"] | payload["SwitchInfo"]
            switch_info = sensors.SwitchInfo(**merged_json)

            def my_callback(client: Client, user_data, message: MQTTMessage):
                payload = message.payload.decode()
                if payload == "ON":
                    # turn_my_custom_thing_on()
                    # Let HA know that the switch was successfully activated
                    switch.on()
                    self.logger.info("ik sta aan")
                elif payload == "OFF":
                    # turn_my_custom_thing_off()
                    # Let HA know that the switch was successfully deactivated
                    self.logger.off()
                    
                    logging.info("ik sta uit")

            switch = sensors.Switch(Settings(mqtt=self.mqtt_settings, entity=switch_info), my_callback)
            
            self.switches.append(switch)
            
            switch.off()
            
            self.logger.info("Switch made and deactivated")
            # self.switches[-1].mqtt_client.message_callback_add(self.switches[-1]._command_topic, my_callback)
            
            # self.mqtt_client.message_callback_add(self._command_topic, my_callback)
            
        self.logger.info("Switch function done")
            # pass
    
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
        entityinfo = sensors.BinarySensorInfo(payload["EntityInfo"])
        if DeviceInfo in payload:
            entityinfo.device = DeviceInfo(payload["DeviceInfo"])
        self.entities.append(sensors.BinarySensor(Settings(mqtt=self.mqtt_settings, entity=entityinfo)))



    #     @self.app.get(self.base_url + 'sys/info')
    #     def krijg_staat(request: Request):
    #         """
    #             This endpoint returns basic system information on the host like CPU temperature (celcius), up time (hours), cpu temperature and memory usage. 
    #         """
    #         cpu_temp = CPUTemperature().temperature
    #         up_time = time.monotonic()/60/60
    #         cpu_percentage = psutil.cpu_percent(interval=1)
    #         memory_usage = psutil.virtual_memory().percent
    #         return self.jsonify({"is_active": "True","cpu_temp": cpu_temp, "up_time": up_time, "cpu_percentage": cpu_percentage, "memory_usage": memory_usage })
        

    #     @self.app.post(self.base_url + 'pin/{pin_type}')
    #     async def post_pin(pin_type: PinType, 
    #                       pin_config = Body(openapi_examples={"in": { 
    #                                                                 "value": {
    #                                                                     "pin": "1",
    #                                                                     "active_state": 1, 
    #                                                                     "pull_up": 1,
    #                                                                     "webhook": "my_home_assisistant_pin_in_1"
    #                                                                     },
    #                                                                 },
    #                                                             "out": {
    #                                                                 "value": {
    #                                                                     "pin": "1",
    #                                                                     "initial": 0,
    #                                                                     "active_state": 1,
    #                                                                     "value": 1,
    #                                                                     "password": "secret",
    #                                                                     "blink": 1
    #                                                                     }, 
    #                                                                 },
    #                                                             "count": {
    #                                                                 "value": {
    #                                                                     "pin": "1",
    #                                                                     "active_state": 1,
    #                                                                     "pull_up": 1,
    #                                                                     "webhook": "my_home_assisistant_pin_count_1"
    #                                                                     },
    #                                                                 },
    #                                                             "nwayout": {
    #                                                                 "value": {
    #                                                                     "pin": 23, 
    #                                                                     "pin_list": [23, 24, -1], 
    #                                                                     "initial": [0, 0 ,0], 
    #                                                                     "active_state": [0, 0, 0], 
    #                                                                     "pin_names": ["stop", "close", "open"], 
    #                                                                     "active_pin": "close"
    #                                                                     },
    #                                                                 },
    #                                                             },
    #                                                         )): 
    #         """
    #             This endpoint allows to create new pins or change the state of an output type pin device. 
    #         """
    #         pin_config['ptype'] = pin_type.value
    #         try:
    #             pin_model = PinModel(pin_config)
    #         except ValidationError as e: # Exception as e
    #             raise HTTPException(status_code=400, detail=str(e))
            
    #         self.logger.info('Posting new (value for) pin: {}'.format(pin_model))
    #         if self.pin_keeper.SetPin(pin_model): 
    #             return self.jsonify(self.pin_keeper.GetPin(pin_model))    


    #     @self.app.get(self.base_url + 'pin/' + PinType.pinin.value)
    #     async def get_pin(pin_config: PinIn= Depends()): 
    #         """
    #             This endpoint allows to retrieve the curent pin state of the specified existin pin. 
    #             Mind that the configuration of the pin must match the saved configuration. In case 
    #             the pin does not exist (due to e.g. reboot), the pin is created according to the 
    #             configuration, like it was a POST.
    #         """
    #         return self.handel_get_request(PinModel(pin_config.model_dump()))

    #     @self.app.get(self.base_url + 'pin/' + PinType.pinout.value)
    #     async def get_pin(pin_config: PinOut= Depends()): 
    #         """
    #             This endpoint allows to retrieve the curent pin state of the specified existin pin. 
    #             Mind that the configuration of the pin must match the saved configuration. In case 
    #             the pin does not exist (due to e.g. reboot), the pin is created according to the 
    #             configuration, like it was a POST.
    #         """
    #         return self.handel_get_request(PinModel(pin_config.model_dump()))

    #     @self.app.get(self.base_url + 'pin/' + PinType.pincount.value)
    #     async def get_pin(pin_config: PinCount= Depends()): 
    #         """
    #             This endpoint allows to retrieve the curent pin state of the specified existin pin. 
    #             Mind that the configuration of the pin must match the saved configuration. In case 
    #             the pin does not exist (due to e.g. reboot), the pin is created according to the 
    #             configuration, like it was a POST.
    #         """
    #         return self.handel_get_request(PinModel(pin_config.model_dump()))

    #     @self.app.get(self.base_url + 'pin/' + PinType.pinnwayout.value)
    #     async def get_pin(pin_config: PinNWayOut = Depends()): 
    #         """
    #             This endpoint allows to retrieve the curent pin state of the specified existin pin. 
    #             Mind that the configuration of the pin must match the saved configuration. In case 
    #             the pin does not exist (due to e.g. reboot), the pin is created according to the 
    #             configuration, like it was a POST.
    #         """
    #         return self.handel_get_request(PinModel(pin_config.model_dump()))
            

    #     self.logger.info('{} started'.format(self.name))


    # def handel_get_request(self, pin_model):
    #         self.logger.info('Getting value of pin: {}'.format(pin_model))
    #         ret = self.pin_keeper.GetPin(pin_model)
    #         if type(ret) == bool: 
    #             return self.jsonify(pin_model.root.model_dump())
    #         else:
    #             return self.jsonify(ret)
    
    # def jsonify(self, json_dict):
    #     return JSONResponse(content=jsonable_encoder(json_dict))
    


