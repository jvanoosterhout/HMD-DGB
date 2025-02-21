#!/usr/bin/env python
# encoding: utf-8
"""
Pin uit class om GPIO pinnen in te stellen als output

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_out(Pin):
    def __init__(self, HASS_interface: Client, config:Pin):
        """
        Initialiseer de Pin_out klasse met standaardwaarden.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin, moet "out" zijn.
        """
        super().__init__(HASS_interface=HASS_interface, config=config)

    def HasSameConfig(self, config:Pin) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if not config.ptype == self.config.ptype:
            self.logger.warning('New "ptype" {} for pin {} is different from known "ptype" {}'.format(config.ptype, self.config.pin, self.config.ptype))
            return False
        if not config.active_state == self.config.active_state:
            self.logger.warning('New "active_state" {} for pin {} is different from known "active_state" {}'.format(config.active_state, self.config.pin, self.config.active_state))
            return False
        return True
    
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalOutputDevice(pin = self.config.pin,
                                              active_high = self.config.active_state,
                                              initial_value = self.config.initial) #, 
                                            #  pin_factory = LGPIOFactory(chip=0))

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
    
    def ProcessPinUpdate(self, config:Pin) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input pins wil only show a log 
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        if config.blink is not None:
            self.pin_device.blink(on_time=config.blink,
                                  off_time=config.blink, 
                                  n=1,
                                  background=True)
            self.logger.info('pin {} has value {} for {} seconds'.format(self.config.pin, not(self.config.initial), config.blink))
        else:
            value = config.value
            if not isinstance(value, int):
                value = int(value)
            self.value = value
            if self.value:
                self.pin_device.on()
                self.logger.info('pin {} is on'.format(self.config.pin))
            else:
                self.pin_device.off()
                self.logger.info('pin {} is off'.format(self.config.pin))
        
        return True
    

