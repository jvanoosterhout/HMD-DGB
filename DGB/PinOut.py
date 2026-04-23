#!/usr/bin/env python
# encoding: utf-8
"""
Pin uit class om GPIO pinnen in te stellen als output

Jeroen van Oosterhout, 15-07-2024
"""

from DGB.Pin import Pin
from gpiozero import DigitalOutputDevice
from DGB.PinModels import PinModel
from DGB.DataStore import DataStore


class Pin_out(Pin):
    def __init__(
        self, config: PinModel, datastore: DataStore, is_PinNWayOut: bool = False
    ):
        """
        Initialiseer de Pin_out klasse met standaardwaarden.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin, moet "out" zijn.
        """
        super().__init__(config=config, datastore=datastore)
        self.is_PinNWayOut = is_PinNWayOut

    def HasSameConfig(self, config: PinModel) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if not config.ptype == self.config.ptype:
            self.logger.warning(
                'New "ptype" {} for pin {} is different from known "ptype" {}'.format(
                    config.ptype, self.config.pin, self.config.ptype
                )
            )
            return False
        if not config.active_state == self.config.active_state:
            self.logger.warning(
                'New "active_state" {} for pin {} is different from known "active_state" {}'.format(
                    config.active_state, self.config.pin, self.config.active_state
                )
            )
            return False
        return True

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalOutputDevice(
            pin=self.config.pin,
            active_high=self.config.active_state,
            initial_value=self.config.initial,
        )  # ,
        #  pin_factory = LGPIOFactory(chip=0))

    def blink(self, blink: int = None, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            if blink is None and self.blink is None:
                self.logger.info(
                    "pin {} is has no blink configured".format(self.config.pin)
                )
                return False
            elif blink is not None:
                on_time = blink
            else:
                on_time = self.blink

            self.pin_device.blink(
                on_time=on_time, off_time=on_time, n=1, background=True
            )
            self.logger.info(
                "pin {} has value {} for {} seconds".format(self.config.pin, 1, on_time)
            )
            return True
        return False

    def on(self, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            self.pin_device.on()
            self.logger.info("pin {} is on".format(self.config.pin))
            return True
        return False

    def off(self, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            self.pin_device.off()
            self.logger.info("pin {} is off".format(self.config.pin))
            return True
        return False

    def ProcessPinUpdate(self, config: PinModel, is_PinNWayOut: bool = False) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally
        this only works for output pins. Input pins wil only show a log
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        if self.is_PinNWayOut == is_PinNWayOut:
            if config.blink is not None:
                return self.blink(blink=config.blink, is_PinNWayOut=is_PinNWayOut)
            else:
                value = config.value
                if not isinstance(value, int):
                    value = int(value)
                if value:
                    return self.on(is_PinNWayOut)
                else:
                    return self.off(is_PinNWayOut)
        return False
