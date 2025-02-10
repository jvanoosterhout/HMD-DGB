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

    def GetPin(self, pin_config_dict:dict):
        """
        Get pin value, if it exists, otherewise try to make it.
        
        Parameters:
        pin_config_dict (dict): Configuration of the pin.

        Returns:
        float/bool/None: Value of the pin or False or None.
        """
        if not pin_config_dict == {}: 
            if 'pin' in pin_config_dict:
                pin_config_dict = self.FormatPin(pin_config_dict)
                if pin_config_dict == {}:
                    return False
                pin_id = self.DoIExist(pin_config_dict)
                if pin_id is None: # no pin config
                    self.logger.info('No pin configuration recognized.')
                    
                elif type(pin_id) == bool: # is pin config, but does not exist jet
                    self.logger.info('is pin config, but does not exist jet.')
                    if self.SetPin(pin_config_dict):
                        pin_id = self.DoIExist(pin_config_dict)
                        return self.PinList[pin_id].GetPinValue()
                else: # is pin config, and it exists --> ask its value
                    self.logger.info('is pin config, and it exists, therefore requesting its value.')
                    return self.PinList[pin_id].GetPinValue()
            else: 
                self.logger.info('is not a pin configuration.')

        self.logger.info('Got an unrecognized configuration.')
        return False

    def SetPin(self, pin_config_dict:dict) -> bool:
        """
        Set the configuration of a pin, in case the pin does not jet exists, it sends to creates one.
        
        Parameters:
        pin_config_dict (dict): Configuratie van de pin.

        Returns:
        bool: True if succesfully made or new settings succesfully processed, otherwise False.
        """
        if not pin_config_dict == {}: 
            if 'pin' in pin_config_dict:
                pin_config_dict = self.FormatPin(pin_config_dict)
                if pin_config_dict == {}:
                    return False
                pin_id = self.DoIExist(pin_config_dict)
                if pin_id is None: # no pin config
                    self.logger.warning('Obtained an unrecognized pin configuration: {}'.format(pin_config_dict))
                    return False
                elif type(pin_id) == bool: # is pin config, but does not exist jet
                    if self.MakeNewPin(pin_config_dict):
                        return True
                    else: 
                        self.logger.warning('No pin configuration recognized.')
                        return False
                else: # is pin config, and exists, thus process update
                    self.logger.info('Proces update.')
                    if self.PinList[pin_id].pin in self.PinPWList:
                        if not self.PinList[pin_id].CheckPW(pin_config_dict["password"]): 
                            self.logger.warning('Worng password!')
                            return False
                    return self.PinList[pin_id].ProcessPinUpdate(pin_config_dict)
            else: 
                self.logger.info('is not a pin configuration.')
        self.logger.warning('Empty config.')
        return False

    def DoIExist(self, pin_config_dict:dict):
        """
        Check if a pin allready exists in PinList.
        
        Parameters:
        pin_config_dict (dict): Configuration of the pin.

        Returns:
        int/bool/None: Index of the pin in the PinList or False or None if something goes terably wrong.
        """
        if 'pin' in pin_config_dict:
            if self.PinList == []:
                return False
            for pin in self.PinList:
                if pin.pin == int(pin_config_dict["pin"]): 
                    return self.PinList.index(pin)
            return False
        self.logger.warning('"pin" id not in config.')
        return None
    
    def MakeNewPin(self, pin_config_dict:dict) -> bool:
        """
        Create a new pin based on the configuration optained from the rest call

        Parameters:
        pin_config_dict (dict): Configuration of the pin.

        Returns:
        bool: True if succesfully made, otherwise False.
        """
        self.logger.info('Maak pin met config: {}'.format(pin_config_dict))
        pw_needed = False
        if pin_config_dict["pin"] in self.PinPWList:
            if 'password' in pin_config_dict:
                if pin_config_dict["password"] == self.PinPWList[pin_config_dict["pin"]]:
                    pw_needed = True
                else:
                    self.logger.warning('Worng password!')
                    return False
            else:
                self.logger.warning('No password provided, while this is required!')
                return False
        if pin_config_dict['type'] is PinType.pinout.value:
            P = Pin_out(pin=pin_config_dict["pin"],HASS_interface=self.HASS_interface, type=pin_config_dict["type"]) 
        elif pin_config_dict['type'] is PinType.pinin.value:
            P = Pin_in(pin=pin_config_dict["pin"],HASS_interface=self.HASS_interface, type=pin_config_dict["type"]) 
        elif pin_config_dict['type'] is PinType.pincount.value:
            P = Pin_count(pin=pin_config_dict["pin"],HASS_interface=self.HASS_interface, type=pin_config_dict["type"]) 
        else:
            return False
        if pw_needed:
            P.pw = {pin_config_dict["pin"]: self.PinPWList[pin_config_dict["pin"]]}
        self.logger.info('Configure pin {}.'.format(P.pin))
        P.PinSetup(pin_config_dict)
        self.logger.info('Add pin {} to PinList'.format(P.pin))
        self.PinList.append(P)
        self.logger.info('Pin {} added to PinList.'.format(P.pin))
        return True

    def FormatPin(self, pin_config_dict:dict) -> dict:
        """
        Format the pin configuration and check on errors. This function will be removed and should be replacesed by BaseModels in PinModels.

        Parameters:
        pin_config_dict (dict): Configuratie van de pin.

        Returns:
        dict: Geformatteerde pin configuratie.
        """
        # if 'pin' in pin_config_dict:
        #     if IOT_tools.is_int(pin_config_dict["pin"]):
        #         pin_config_dict["pin"] = int(pin_config_dict["pin"])
        #     else:
        #         self.logger.error('"pin" incorrect gedefineerd voor pin {}'.format(self.pin)) 
        #         return {}
        # else:
        #     self.logger.error('"pin" incorrect gedefineerd voor pin {}'.format(self.pin)) 
        #     return {}
        
        # if not 'type' in pin_config_dict: 
        #     self.logger.error('Geen "type" gedefineerd voor pin {}'.format(self.pin))
        #     return {}
        # elif is_pin_type(pin_config_dict['type']):
        #     if pin_config_dict['type'] is PinType.pinout:
        #         if pin_config_dict['initial'] == None:
        #             self.logger.warning('Geen "initial" gedefineerd voor pin {}, neem aan dat het 0 is'.format(self.pin))     
        #             pin_config_dict["initial"] = 0
        #         else: 
        #             if IOT_tools.is_int(pin_config_dict["initial"]):
        #                 pin_config_dict["initial"] = int(pin_config_dict["initial"])
        #             else:
        #                 self.logger.warning('"initial" incorrect gedefineerd voor pin {}, neem aan dat het 0 is'.format(self.pin)) 
        #                 pin_config_dict["initial"] = 0
        #         if pin_config_dict['value'] == None:
        #             pin_config_dict["value"] = pin_config_dict["initial"]
        #             self.logger.warning('ik vond geen value in pin_config_dict, dus neem aan dat de initial goed is')
        # else:
        #     self.logger.error('niet bestaande "type": "{}" gedefineerd voor pin {}'.format(pin_config_dict['type'], pin_config_dict['pin']))
        #     return {}   
        
        # if "blink" in pin_config_dict:
        #     if pin_config_dict["blink"] is not None:
        #         if IOT_tools.is_int(pin_config_dict["blink"]):
        #             pin_config_dict["blink"] = int(pin_config_dict["blink"])
        #         else: 
        #             self.logger.error('"blink" incorrect gedefineerd voor pin {}, de key wordt verwijderd'.format(self.pin))
        #             del pin_config_dict["blink"]
        #     else: 
        #         del pin_config_dict["blink"]
        
        return pin_config_dict
    
        