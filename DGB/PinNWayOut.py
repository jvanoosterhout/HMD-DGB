#!/usr/bin/env python
# encoding: utf-8
"""
Pin uit class om GPIO pinnen in te stellen als output

Jeroen van Oosterhout, 15-07-2024
"""

from DGB.PinOut import Pin_out
from DGB.PinModels import PinType, PinModel
from DGB.Pin import Pin
from gpiozero import DigitalOutputDevice
from DGB.DataStore import DataStore


class Pin_N_way_out(Pin):
    def __init__(self, config: PinModel, datastore: DataStore):
        """
        Initialiseer the Pin_N_way_out class.

        Parameters:
        config (Pin rootmodel): the pin configuration.
        """
        super().__init__(config=config, datastore=datastore)
        self.Pins: list[Pin_out] = []

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
        if not config.pin_list == self.config.pin_list:
            self.logger.warning(
                'New "pin_list" {} for pin {} is different from known "pin_list" {}'.format(
                    config.pin_list, self.config.pin, self.config.pin_list
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
        if not config.pin_names == self.config.pin_names:
            self.logger.warning(
                'New "pin_names" {} for pin {} is different from known "pin_names" {}'.format(
                    config.pin_names, self.config.pin, self.config.pin_names
                )
            )
            return False
        return True

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        n = self.GetPinIndex(self.config.pin)
        self.pin_device = DigitalOutputDevice(
            pin=self.config.pin,
            active_high=self.config.active_state[n],
            initial_value=self.config.initial[n],
        )  # ,
        #  pin_factory = LGPIOFactory(chip=0))

    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """

        res = bool(self.pin_device.value)
        for p in self.Pins:
            res = res or bool(p.pin_device.value)
        # res = False
        # if isinstance(self.value, int):
        #     res = bool(self.value)
        # elif isinstance(self.value, bool):
        #     res = self.value
        # else:
        #     res = IOT_tools.strtobool(self.value)

        if self.config.active_pin is None:
            active_pin = None
            active_pin_name = "off"
        else:
            n = self.GetPinIndex(self.config.active_pin)
            active_pin = self.config.pin_list[n]
            active_pin_name = self.config.pin_names[n]

        return {
            "is_active": res,
            "active_pin": active_pin,
            "active_pin_name": active_pin_name,
        }

    def GetPinIndex(self, active_pin) -> int:
        n = -1
        if isinstance(active_pin, str):
            if active_pin in self.config.pin_names:
                n = self.config.pin_names.index(active_pin)
        if isinstance(active_pin, int):
            if active_pin in self.config.pin_list:
                n = self.config.pin_list.index(active_pin)
        return n

    def GenerateSubPinConfig(self, n: int) -> PinModel:
        return PinModel(
            {
                "pin": self.config.pin_list[n],
                "ptype": PinType.pinout.value,
                "initial": self.config.initial[n],
                "active_state": self.config.active_state[n],
            }
        )

    # def blink(self, blink:int = None) -> bool:
    #     if blink is None  and self.blink is None:
    #         self.logger.info('pin {} is has no blink configured'.format(self.config.pin))
    #         return False
    #     elif blink is not None:
    #         on_time = blink
    #     else :
    #         on_time = self.blink

    #     self.pin_device.blink(on_time=on_time,
    #                             off_time=on_time,
    #                             n=1,
    #                             background=True)
    #     self.logger.info('pin {} has value {} for {} seconds'.format(self.config.pin, 1, on_time))
    #     return True

    def on(self, active_pin: int) -> bool:
        self.off()

        if active_pin is None:
            self.config.active_pin = None
            return True
        n = self.GetPinIndex(active_pin)

        if n == -1:
            return False
        if self.config.pin_list[n] == -1:
            self.logger.info(
                'N Way Out dummy pin with name "{}" turned on'.format(
                    self.config.pin_names[n]
                )
            )
            self.config.active_pin = active_pin
            return True

        if not self.config.pin_list[n] == self.config.pin:
            for p in self.Pins:
                if p.config.pin == self.config.pin_list[n]:
                    p.on(is_PinNWayOut=True)
        else:
            self.pin_device.on()
            self.config.value = 1

        self.logger.info(
            'N Way Out pin {} with name "{}" turned on'.format(
                self.config.pin_list[n], self.config.pin_names[n]
            )
        )

        self.config.active_pin = active_pin

        return True

    def off(self) -> bool:
        for p in self.Pins:
            p.off(is_PinNWayOut=True)
        self.pin_device.off()
        self.config.value = 0
        self.logger.info("All N Way Out pins turned off")
        return True

    def ProcessPinUpdate(self, config: PinModel) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally
        this only works for output pins. Input pins wil only show a log
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        return self.on(active_pin=config.active_pin)
