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

from DGB.Pin import Pin
from gpiozero import DigitalInputDevice
from DGB.PinModels import PinModel
from DGB.DGBContext import DGBContext
import time


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
        if not config.pull_up == self.config.pull_up:
            self.logger.warning(
                'New "pull_up" {} for pin {} is different from known "pull_up" {}'.format(
                    config.pull_up, self.config.pin, self.config.pull_up
                )
            )
            return False
        if not config.when_activated == self.config.when_activated:
            self.logger.warning(
                'New "when_activated" {} for pin {} is different from known "when_activated" {}'.format(
                    config.when_activated,
                    self.config.pin,
                    self.config.when_activated,
                )
            )
            return False
        if not config.when_deactivated == self.config.when_deactivated:
            self.logger.warning(
                'New "when_deactivated" {} for pin {} is different from known "when_deactivated" {}'.format(
                    config.when_deactivated,
                    self.config.pin,
                    self.config.when_deactivated,
                )
            )
            return False
        if not config.scaling_factor == self.config.scaling_factor:
            self.logger.warning(
                'New "scaling_factor" {} for pin {} is different from known "scaling_factor" {}'.format(
                    config.scaling_factor,
                    self.config.pin,
                    self.config.scaling_factor,
                )
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

    def is_update_relevant(self):
        """
        Controller of er voldoende pulsen geteld of tijd verstreken
        zijn om een update naar HASS te versturen.

        Returns:
        bool: True als de update versturen een goed idee is, anders False.
        """
        tot_nog_geteld = self.count_total - self.count_laatste_blok
        if tot_nog_geteld == 0:
            self.logger.info("geen counts sinds laatste update")
            return False
        tijd_sinds_laatste_count = time.monotonic() - self.tijd_laatste_count
        print(tot_nog_geteld)
        print(tijd_sinds_laatste_count)
        if tijd_sinds_laatste_count > 60 * 5:
            self.logger.info(
                "laatste update langer dan 5 minuten geleden, met nog een rest waarde"
            )
            return True
        elif tijd_sinds_laatste_count > 60 and tot_nog_geteld > 5:
            self.logger.info(
                "laatste update langer dan 1 minuten geleden, met minimaal 5 counts"
            )
            return True
        elif tijd_sinds_laatste_count > 30 and tot_nog_geteld > 10:
            self.logger.info(
                "laatste update langer dan 30 seconden geleden, met minimaal 10 counts"
            )
            return True
        elif tijd_sinds_laatste_count > 10 and tot_nog_geteld > 50:
            self.logger.info(
                "laatste update langer dan 10 seconden geleden, met minimaal 50 counts"
            )
            return True
        elif tot_nog_geteld > 100:
            self.logger.info("binnen 10 seconden meer dan 100 counts")
            return True
        self.logger.info("geen update nodig")
        return False

    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """
        duur = time.monotonic() - self.tijd_laatste_block
        count_laatste_blok = self.count_total - self.count_laatste_blok
        if duur > 0.0:
            self.stroom = count_laatste_blok * 1.0 / duur / self.calibrationFactor
        else:
            self.stroom = 0

        self.tijd_laatste_block = time.monotonic()
        self.count_laatste_blok = self.count_total
        scaled_total = self.count_total / self.config.scaling_factor
        self.logger.info(
            "pin {} has {} counts total, with {} counts the last {} s, and a flow of {} per second".format(
                self.config.pin,
                self.count_total,
                count_laatste_blok,
                duur,
                self.stroom,
            )
        )
        return {
            "totaal": scaled_total,
            "count_total": scaled_total,
            "stroom": self.stroom,
        }

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
            "pin {} heeft {} tellen totaal, met een stroom van {} per seconde".format(
                self.config.pin, self.count_total, self.stroom
            )
        )
        return True
