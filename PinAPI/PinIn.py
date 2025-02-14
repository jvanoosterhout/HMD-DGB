#!/usr/bin/env python
# encoding: utf-8
"""
Generieke pin configurator class

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_in(Pin):
    def __init__(self, HASS_interface: Client, pin, type):
        if not type == "in":
            self.logger.error('Verkeerde type. Kreeg "{}", verwachte "out"'.format(type))
            return False
        super().__init__(pin=pin, HASS_interface=HASS_interface, type=type)


    def HasSameConfig(self, pin_config_dict:dict) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if not pin_config_dict["type"] == self.type:
            self.logger.info('Nieuwe "type" {} voor pin {} is anders dan bekend "type" {}'.format(pin_config_dict["type"], self.pin, self.type))
            return False
        if not pin_config_dict["active_state"] == self.active_state:
            self.logger.info('Nieuwe "active_state" {} voor pin {} is anders dan bekend "active_state" {}'.format(pin_config_dict["active_state"], self.pin, self.active_state))
            return False
        if not pin_config_dict["pull_up"] == self.pull_up:
            self.logger.info('Nieuwe "pull_up" {} voor pin {} is anders dan bekend "pull_up" {}'.format(pin_config_dict["pull_up"], self.pin, self.pull_up))
            return False
        return True
    
    def SavePin(self, pin_config_dict:dict):
        """
        Save the pin configuration in this object.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.
        """
        self.pin = pin_config_dict["pin"]  
        # self.initial = pin_config_dict["initial"]  
        self.active_state = pin_config_dict["active_state"] 
        self.pull_up = pin_config_dict["pull_up"]
        # if "password" in pin_config_dict:
        #     self.password = pin_config_dict["password"]  
        # else: 
        #     self.password = ""
        if pin_config_dict['webhook'] is not None : 
            self.webhook = pin_config_dict['webhook'] 
                
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(pin = self.pin, 
                                             pull_up = self.pull_up,
                                             bounce_time = 0.01) #,
                                            #  active_state = self.active_state, 
                                            #  pin_factory = LGPIOFactory(chip=0))
        self.pin_device.when_activated = self.calback
        self.pin_device.when_deactivated = self.calback
        self.calback()

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device. 

        Function:
        - measure the current pin state (on/off) and store it.
        - In case a webhook was provided, send a POST call to the Home Assistant API with the current pin value.
        """
        value = self.pin_device.value
        if not self.active_state:
            value = int(not value == 1)
        self.value = value

        if not self.webhook == "" and not self.webhook is None:
            path = 'webhook/{}'.format(self.webhook)
            headers={"Content-Type" : "application/json"}
            data = {"{}".format(self.webhook): self.value}
            # self.logger.info(json.dumps(data))
            self.HASS_interface.request(path = path, method="POST", headers=headers, data=json.dumps(data))
            self.logger.info('pin {} update verstuurd'.format(self.pin))

        self.logger.info('pin {} heeft een signaal {}'.format(self.pin, self.value))

    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """
        res = False
        if isinstance(self.value, int):
            res = bool(self.value)
        elif isinstance(self.value, bool):
            res = self.value
        else: 
            res = IOT_tools.strtobool(self.value)
        return {"is_active": res}
    
    def ProcessPinUpdate(self, pin_config_dict:dict) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input pins wil only show a log 
        message with their current state.

        Parameters:
        pin_config_dict (dict): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        if not self.HasSameConfig(pin_config_dict):
            return False
        if self.value:
            self.logger.info('pin {} heeft een hoog signaal'.format(self.pin))
        else:
            self.logger.info('pin {} heeft een laag signaal'.format(self.pin))
        return True


