#!/usr/bin/env python
# encoding: utf-8
"""
Generic pin class

Jeroen van Oosterhout, 15-07-2024
"""
import json
import time
import logging
from PinAPI.Tools import IOT_tools
from gpiozero import DigitalOutputDevice, DigitalInputDevice
# from gpiozero.pins.lgpio import LGPIOFactory
from homeassistant_api import Client

 
class Pin(object):
    def __init__(self, HASS_interface: Client, pin:int=-1, ptype:str="pin"):
        """
        Initialiseer the Pin class.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin.
        """
        self.pin = pin 
        self.pin_device = None
        self.type = ptype  
        self.initial = 1 
        self.active_state = True 
        self.pull_up = True 
        self.value = 0 
        self.password = "NULL" 
        self.webhook = "" 
        self.rate = 0 
        self.last_changed = time.monotonic()
        
        self.pw = {}
        self.HASS_interface = HASS_interface
        
        self.logger = logging.getLogger("pin_{}_{}".format(self.type, self.pin))
        self.logger.info('Configuring pin {}.'.format(self.pin))
        logging.getLogger().setLevel(logging.INFO)
   
        
    def PinSetup(self, pin_config_dict:dict) -> bool:
        """
        Setup the pin based on the configuration.

        Parameters:
        pin_config_dict (dict): Configuration of the pin.

        Returns:
        bool: True if the pin is succesfully setup, otherwise False.
        """
        # if self.pin in self.pw:
        #     if 'password' in pin_config_dict:
        #         if pin_config_dict['password'] is not None or pin_config_dict['password'] == "":
        #             if not self.check_pw(pin_config_dict['password']):
        #                 self.logger.warning('Verkeerde paswoord!')
        #                 return False
        #         else:
        #             self.logger.warning('Geen paswoord, waar dit wel vereist is!')
        #             return False
        #     else:
        #         self.logger.warning('Geen paswoord, waar dit wel vereist is!')
        #         return False
    
        self.SavePin(pin_config_dict)
        self.ConfigurePin()
        if self.ProcessPinUpdate(pin_config_dict):
            return True       
        else:
            self.logger.error("Kon pin waarde niet zetten")
            return False

    def HasSameConfig(self, pin_config_dict:dict) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        return False
 
    def SavePin(self, pin_config_dict:dict):
        """
        Save the pin configuration in this object.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.
        """
        pass

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        pass

    def ProcessPinUpdate(self, pin_config_dict:dict) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input device type pins wil only show a log 
        message with their current state.

        Parameters:
        pin_config_dict (dict): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        return False
    
    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """
        return {"is_active": False}

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device. 
        """
        pass

    def CheckPW(self, pw: str) -> bool:
        """
        Check if the correct password was provided for this pin.

        Parameters:
        pw (str): the password.

        Returns:
        bool: True if the password is correct, otherwise False.
        """
        if pw.lower() == self.pw[self.pin]:
            return True
        else:
            return False

    def update(self): 
        pass
