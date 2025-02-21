#!/usr/bin/env python
# encoding: utf-8
"""
Pin keeper class to create and manage all pins 

Jeroen van Oosterhout, 15-07-2024
"""

from PinAPI.PinOut import Pin_out
from PinAPI.PinIn import Pin_in
from PinAPI.PinCount import Pin_count
from PinAPI.Pin import Pin
from PinAPI.Tools import IOT_tools
from PinAPI.PinModels import is_pin_type, PinType
import logging
import time
from homeassistant_api import Client

class PinKeeper(object):
    def __init__(self, api_url:str="http://IP-ADRES:8123/api/", token:str="secret",pin_pw_list:dict={}):
        """
        Initialize the PinKeeper class with default values.
        """
        self.PinPWList = pin_pw_list
        self.PinList: list[Pin] = []
        self.logger = logging.getLogger("PinKeeper")
        logging.getLogger().setLevel(logging.INFO)

        self.HASS_interface = Client(api_url=api_url, token=token, verify_ssl=False)
        while not self.check_HASS():
            self.logger.info('This host cannot (jet) connect to Home Assistant at {}.'.format(api_url))
            time.sleep(10)

        self.logger.info('PinKeeper initialized.')


    def __del__(self):
        for pin in self.PinList:
            pin.pin_device.close()
        self.logger.info('PinKeeper cleaned up all pins')
        
    def check_HASS(self) -> bool:
        """
        Check if Home Assistant is available at the given url.

        Returns:
            bool: True if succesfully connected to Home Assistant API, otherwise False.
        """
        try:
            return self.HASS_interface.check_api_running()
        except : # requests.exceptions.ConnectionError as e:
            return False 

    def GetPin(self, config:Pin):
        """
        Get pin value, if it exists, otherewise try to make it.
        
        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        float/bool/None: Value of the pin or False or None.
        """
        pin_id = self.DoIExist(config)
        if pin_id is None: # no pin config
            self.logger.info('No pin configuration recognized.')
            
        elif type(pin_id) == bool: # is pin config, but does not exist jet
            self.logger.info('is pin config, but does not exist jet.')
            if self.SetPin(config):
                pin_id = self.DoIExist(config)
                return self.PinList[pin_id].GetPinValue()
        else: # is pin config, and it exists --> ask its value
            self.logger.info('is pin config, and it exists, therefore requesting its value.')
            return self.PinList[pin_id].GetPinValue()
          
        self.logger.info('Got an unrecognized configuration.')
        return False

    def SetPin(self, config:Pin) -> bool:
        """
        Set the configuration of a pin, in case the pin does not jet exists, it sends to creates one.
        
        Parameters:
        config (Pin): Configuratie van de pin.

        Returns:
        bool: True if succesfully made or new settings succesfully processed, otherwise False.
        """
        pin_id = self.DoIExist(config)
        if pin_id is None: # no pin config
            self.logger.warning('Obtained an unrecognized pin configuration: {}'.format(config))
            return False
        elif type(pin_id) == bool: # is pin config, but does not exist jet
            if self.MakeNewPin(config):
                return True
            else: 
                self.logger.warning('No pin configuration recognized.')
                return False
        else: # is pin config, and exists, thus process update
            self.logger.info('Proces update.')
            if self.PinList[pin_id].config.pin in self.PinPWList:
                if not self.PinList[pin_id].CheckPW(config.password): 
                    self.logger.warning('Worng password!')
                    return False
            if self.PinList[pin_id].HasSameConfig(config):
                return self.PinList[pin_id].ProcessPinUpdate(config)
            else:
                return False

    def DoIExist(self, config:Pin):
        """
        Check if a pin allready exists in PinList.
        
        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        int/bool: Index of the pin in the PinList or False.
        """
        
        if self.PinList == []:
            return False
        for pin in self.PinList:
            if pin.config.pin == config.pin: 
                return self.PinList.index(pin)
        return False

    
    def MakeNewPin(self, config:Pin) -> bool:
        """
        Create a new pin based on the configuration optained from the rest call

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        bool: True if succesfully made, otherwise False.
        """
        self.logger.info('Maak pin met config: {}'.format(config))
        pw_needed = False
        if config.pin in self.PinPWList:
            if config.password is not None:
                if config.password == self.PinPWList[config.pin]:
                    pw_needed = True
                else:
                    self.logger.warning('Worng password!')
                    return False
            else:
                self.logger.warning('No password provided, while this is required!')
                return False
        if config.ptype is PinType.pinout.value:
            P = Pin_out(HASS_interface=self.HASS_interface, config=config) 
        elif config.ptype is PinType.pinin.value:
            P = Pin_in(HASS_interface=self.HASS_interface, config=config) 
        elif config.ptype is PinType.pincount.value:
            P = Pin_count(HASS_interface=self.HASS_interface, config=config) 
        else:
            return False
        if pw_needed:
            P.pw = {config.pin: self.PinPWList[config.pin]}
        self.logger.info('Configure pin {}.'.format(P.config.pin))
        P.PinSetup(config)
        self.logger.info('Add pin {} to PinList'.format(P.config.pin))
        self.PinList.append(P)
        self.logger.info('Pin {} added to PinList.'.format(P.config.pin))
        return True

    
    
        