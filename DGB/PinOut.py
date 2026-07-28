#
#    Copyright 2024-2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#
#    Pin uit class om GPIO pinnen in te stellen als output

from __future__ import annotations

from gpiozero import DigitalOutputDevice

from DGB.DGBContext import DGBContext
from DGB.Pin import Pin
from DGB.PinModels import PinModel


class Pin_out(Pin):
    def __init__(
        self, config: PinModel, dgb_context: DGBContext, is_PinNWayOut: bool = False
    ):
        """
        Initialiseer de Pin_out klasse met standaardwaarden.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin, moet "out" zijn.
        """
        super().__init__(config=config, dgb_context=dgb_context)
        self.is_PinNWayOut = is_PinNWayOut

    def HasSameConfig(self, config: PinModel) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if config.ptype != self.config.ptype:
            self.logger.warning(
                f'New "ptype" {config.ptype} for pin {self.config.pin} is different from known "ptype" {self.config.ptype}'
            )
            return False
        if config.active_state != self.config.active_state:
            self.logger.warning(
                f'New "active_state" {config.active_state} for pin {self.config.pin} is different from known "active_state" {self.config.active_state}'
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

    def blink(self, blink: int | None = None, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            if blink is None and self.blink is None:
                self.logger.info(f"pin {self.config.pin} is has no blink configured")
                return False
            elif blink is not None:
                on_time = blink
            else:
                on_time = self.blink

            self.pin_device.blink(
                on_time=on_time, off_time=on_time, n=1, background=True
            )
            self.logger.info(
                f"pin {self.config.pin} has value {1} for {on_time} seconds"
            )
            return True
        return False

    def on(self, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            self.pin_device.on()
            self.logger.info(f"pin {self.config.pin} is on")
            return True
        return False

    def off(self, is_PinNWayOut: bool = False) -> bool:
        if self.is_PinNWayOut == is_PinNWayOut:
            self.pin_device.off()
            self.logger.info(f"pin {self.config.pin} is off")
            return True
        return False

    def set_state(self, state_name: str, value: int | str | bool) -> bool:
        if state_name == "blink":
            try:
                value = int(value)
            except (TypeError, ValueError):
                self.logger.warning(
                    "pin %s blink state rejected: %r", self.config.pin, value
                )
                return False
            result = self.blink(blink=value, is_PinNWayOut=self.is_PinNWayOut)
        elif state_name != "state":
            self.logger.warning(
                "pin %s unsupported state name %r", self.config.pin, state_name
            )
            return False

        if isinstance(value, bool):
            value = "on" if value else "off"
        else:
            value = str(value).lower().strip()

        if value in {"on", "1"}:
            result = self.on(is_PinNWayOut=self.is_PinNWayOut)
        elif value in {"off", "0"}:
            result = self.off(is_PinNWayOut=self.is_PinNWayOut)
        else:
            self.logger.warning(
                "pin %s unsupported state value %r", self.config.pin, value
            )
            return False

        if result and self.dgb_context.is_retain_required(str(self.config.pin)):
            self.dgb_context.publish_state_value(
                str(self.config.pin), state_name, value
            )
        return result

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
