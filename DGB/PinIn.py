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
#    pin in configurator class

from DGB.Pin import Pin
from gpiozero import DigitalInputDevice
from DGB.PinModels import PinModel
from DGB.DGBContext import DGBContext


class Pin_in(Pin):
    def __init__(self, config: PinModel, dgb_context: DGBContext):
        super().__init__(config=config, dgb_context=dgb_context)

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
        return True

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(
            pin=self.config.pin, pull_up=self.config.pull_up, bounce_time=0.01
        )
        #  active_state = self.config.active_state) #
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
        # if not self.config.active_state:
        #     value = int(not value == 1)
        # self.value = value

        self.logger.info("Pin {} is: {}".format(self.config.pin, value))
        self.dgb_context.put_to_binder_queue(
            "post", {"unique_id": str(self.config.pin), "payload": value}
        )

        self.logger.info("pin {} has signal {}".format(self.config.pin, value))

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
            "pin {} has signal {}".format(self.config.pin, self.pin_device.value)
        )
        return True
