#!/usr/bin/env python
# encoding: utf-8
"""
Generieke pin configurator class

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_in(Pin):
    def __init__(self, HASS_interface: Client, config:Pin):
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
        if not config.pull_up == self.config.pull_up:
            self.logger.warning('New "pull_up" {} for pin {} is different from known "pull_up" {}'.format(config.pull_up, self.config.pin, self.config.pull_up))
            return False
        return True
                
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(pin = self.config.pin, 
                                             pull_up = self.config.pull_up,
                                             bounce_time = 0.01) #,
                                            #  active_state = self.config.active_state, 
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
        if not self.config.active_state:
            value = int(not value == 1)
        self.value = value

        if not self.config.webhook == "" and not self.config.webhook is None:
            path = 'webhook/{}'.format(self.config.webhook)
            headers={"Content-Type" : "application/json"}
            data = {"{}".format(self.config.webhook): self.value}
            # self.logger.info(json.dumps(data))
            self.HASS_interface.request(path = path, method="POST", headers=headers, data=json.dumps(data))
            self.logger.info('pin {} update send'.format(self.config.pin))

        self.logger.info('pin {} has signal {}'.format(self.config.pin, self.value))

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
        self.logger.info('pin {} has signal {}'.format(self.config.pin, self.value))


