#!/usr/bin/env python
# encoding: utf-8
"""
Pin uit class om GPIO pinnen in te stellen als output

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_out(Pin):
    def __init__(self, HASS_interface: Client, pin, type):
        """
        Initialiseer de Pin_out klasse met standaardwaarden.

        Parameters:
        pin (int): Het pin nummer.
        type (str): Het type pin, moet "out" zijn.
        """
        if not type == "out":
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
        return True
    
    def SavePin(self, pin_config_dict:dict):
        """
        Save the pin configuration in this object.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.
        """
        self.pin = pin_config_dict["pin"]  
        self.initial = pin_config_dict["initial"]  
        self.active_state = pin_config_dict["active_state"] 
        self.value = pin_config_dict["value"]  
        if pin_config_dict["password"] is not None:
            self.password = pin_config_dict["password"]  
        else: 
            self.password = ""
    
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalOutputDevice(pin = self.pin,
                                              active_high = self.active_state,
                                              initial_value = self.initial, 
                                             pin_factory = LGPIOFactory(chip=0))

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

        if pin_config_dict["blink"] is not None:
            self.pin_device.blink(on_time=pin_config_dict["blink"],
                                  off_time=pin_config_dict["blink"], 
                                  n=1,
                                  background=True)
            self.logger.info('pin {} staat {} sec op {}'.format(self.pin, pin_config_dict["blink"], not(self.initial)))
        else:
            value = pin_config_dict['value']
            if not isinstance(value, int):
                value = int(value)
            self.value = value
            if self.value:
                self.pin_device.on()
                self.logger.info('pin {} staat aan'.format(self.pin))
            else:
                self.pin_device.off()
                self.logger.info('pin {} staat uit'.format(self.pin))
        
        return True
    

