#!/usr/bin/env python
# encoding: utf-8
"""
Generic pin class

Jeroen van Oosterhout, 15-07-2024
"""
import json
import time
import logging
from DGB.Tools import IOT_tools
from gpiozero import DigitalOutputDevice, DigitalInputDevice
# from gpiozero.pins.lgpio import LGPIOFactory
from DGB.PinModels import PinModel
from homeassistant_api import Client
# from PinAPI.Binder import Binder
from durable.lang import post
from DGB.DataStore import DataStore

 
class Pin(object):
    def __init__(self, config:PinModel, datastore:DataStore):
        """
        Initialiseer the Pin class.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin.
        """
        self.config:PinModel = config
        self.pin_device = None
        # self.value = 0 

        self.rate = 0 
        self.last_changed = time.monotonic()
        self.pw = {}
        self.HASS_interface = None
        self.datastore = datastore
        
        self.logger = logging.getLogger("pin_{}_{}".format(self.config.ptype, self.config.pin))
        self.logger.info('Configuring pin {}.'.format(self.config.pin))
        logging.getLogger().setLevel(logging.INFO)
   
    def HasSameConfig(self, config:PinModel) -> bool:
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

    def on(self, **kwargs) -> bool:
        return False

    def off(self, **kwargs) -> bool:
        return False

    def ProcessPinUpdate(self, config:PinModel) -> bool:
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

        res = bool(self.pin_device.value)
        return {"is_active": res}

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

    def sendWebhook(self, data_dict:dict):
        if "webhook" in self.config.root.model_dump() and not self.HASS_interface is None:
            if not self.config.webhook == "" and not self.config.webhook is None:
                path = 'webhook/{}'.format(self.config.webhook)
                headers={"Content-Type" : "application/json"}
                self.logger.info("Sending the following data to webhook: {}".format(json.dumps(data_dict)))
                self.HASS_interface.request(path = path, method="POST", headers=headers, data=json.dumps(data_dict))
        pass
