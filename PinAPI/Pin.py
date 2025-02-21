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
from PinAPI.PinModels import Pin
from homeassistant_api import Client

 
class Pin(object):
    def __init__(self, HASS_interface: Client, config:Pin):
        """
        Initialiseer the Pin class.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin.
        """
        self.config = config
        self.pin_device = None
        self.value = 0 

        self.rate = 0 
        self.last_changed = time.monotonic()
        self.pw = {}
        self.HASS_interface = HASS_interface
        
        self.logger = logging.getLogger("pin_{}_{}".format(self.config.ptype, self.config.pin))
        self.logger.info('Configuring pin {}.'.format(self.config.pin))
        logging.getLogger().setLevel(logging.INFO)
   
        
    def PinSetup(self, config:Pin) -> bool:
        """
        Setup the pin based on the configuration.

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        bool: True if the pin is succesfully setup, otherwise False.
        """
        self.ConfigurePin()
        if self.ProcessPinUpdate(config):
            return True       
        else:
            self.logger.error("Could not set pin update")
            return False

    def HasSameConfig(self, config:Pin) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        return False
 
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        pass

    def ProcessPinUpdate(self, config:Pin) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input device type pins wil only show a log 
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

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
        if pw.lower() == self.pw[self.config.pin]:
            return True
        else:
            return False

    def update(self): 
        pass
