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
#    Pin count configurator class


import time

from gpiozero import DigitalInputDevice

from DGB.DGBContext import DGBContext
from DGB.Pin import Pin
from DGB.PinModels import PinModel


class Pin_count(Pin):
    def __init__(self, config: PinModel, dgb_context: DGBContext):
        super().__init__(config=config, dgb_context=dgb_context)
        self.count_total = 0
        self.tijd_laatste_count = time.monotonic()
        self.count_laatste_blok = 0
        self.tijd_laatste_block = time.monotonic()
        self.stroom = 0  # pulsen per minut

        self.calibrationFactor = 1  # 6.6

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
        if config.pull_up != self.config.pull_up:
            self.logger.warning(
                f'New "pull_up" {config.pull_up} for pin {self.config.pin} is different from known "pull_up" {self.config.pull_up}'
            )
            return False
        if config.when_activated != self.config.when_activated:
            self.logger.warning(
                f'New "when_activated" {config.when_activated} for pin {self.config.pin} is different from known "when_activated" {self.config.when_activated}'
            )
            return False
        if config.when_deactivated != self.config.when_deactivated:
            self.logger.warning(
                f'New "when_deactivated" {config.when_deactivated} for pin {self.config.pin} is different from known "when_deactivated" {self.config.when_deactivated}'
            )
            return False
        if config.scaling_factor != self.config.scaling_factor:
            self.logger.warning(
                f'New "scaling_factor" {config.scaling_factor} for pin {self.config.pin} is different from known "scaling_factor" {self.config.scaling_factor}'
            )
            return False
        return True

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(
            pin=self.config.pin, pull_up=self.config.pull_up, bounce_time=None
        )  # ,
        #  active_state = self.config.active_state,
        #  pin_factory = LGPIOFactory(chip=0))
        self.pin_device.when_activated = (
            self.calback if self.config.when_activated else None
        )
        self.pin_device.when_deactivated = (
            self.calback if self.config.when_deactivated else None
        )
        self.calback()

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device.

        Functie:
        - Adds one to the pin total count.
        - Updates the time of the last count.
        - Checks wether a update is relevant to send (don't want to sent an update every count).
        - In case a webhook was provided, send a POST call to the Home Assistant API with the current pin total count and the rate of change sinds the last update.
        """
        self.count_total = self.count_total + 1
        self.tijd_laatste_count = time.monotonic()
        scaled_total = self.count_total / self.config.scaling_factor

        self.dgb_context.put_to_binder_queue(
            "post", {"unique_id": str(self.config.pin), "payload": scaled_total}
        )
        if self.dgb_context.is_retain_required(str(self.config.pin)):
            self.dgb_context.publish_state_to_retain(
                str(self.config.pin),
                "set_state",
                {"args": [{"state_name": "count_total", "state": self.count_total}]},
            )

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
        self.logger.info(
            f"pin {self.config.pin} heeft {self.count_total} tellen totaal, met een stroom van {self.stroom} per seconde"
        )
        return True

    def set_state(self, state_name: str, state: float) -> bool:
        if state_name not in {"scaled_total", "count_total"}:
            self.logger.warning(
                "pin %s unsupported state name %r", self.config.pin, state_name
            )
            return False

        try:
            total = float(state)
        except (TypeError, ValueError):
            self.logger.warning(
                "pin %s rejected retained count value %r for %s",
                self.config.pin,
                state,
                state_name,
            )
            return False

        if state_name == "scaled_total":
            total = total * self.config.scaling_factor

        self.count_total = int(total)
        self.count_laatste_blok = 0
        self.tijd_laatste_count = time.monotonic()
        self.tijd_laatste_block = self.tijd_laatste_count

        self.logger.info("pin %s total restored to %s", self.config.pin, total)
        return True
