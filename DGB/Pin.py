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
#    Generic pin class


import logging
import time

from DGB.DGBContext import DGBContext
from DGB.PinModels import PinModel


class Pin:
    def __init__(self, config: PinModel, dgb_context: DGBContext):
        """
        Initialiseer the Pin class.

        Parameters:
        pin (int): Het pin nummer.
        ptype (str): Het type pin.
        """
        self.config: PinModel = config
        self.pin_device = None
        # self.value = 0

        self.rate = 0
        self.last_changed = time.monotonic()
        self.pw = {}
        self.HASS_interface = None
        self.dgb_context = dgb_context

        self.logger = logging.getLogger(f"pin_{self.config.ptype}_{self.config.pin}")
        self.logger.info(f"Configuring pin {self.config.pin}.")
        logging.getLogger().setLevel(logging.INFO)

    def HasSameConfig(self, config: PinModel) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        return False

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """

    def on(self, **kwargs) -> bool:
        return False

    def off(self, **kwargs) -> bool:
        return False

    def ProcessPinUpdate(self, config: PinModel) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally
        this only works for output pins. Input device type pins wil only show a log
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        return False

    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """

        res = bool(self.pin_device.value)
        return {"is_active": res}

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device.
        """

    def CheckPW(self, pw: str) -> bool:
        """
        Check if the correct password was provided for this pin.

        Parameters:
        pw (str): the password.

        Returns:
        bool: True if the password is correct, otherwise False.
        """
        return pw.lower() == self.pw[self.config.pin]

    def update(self):
        pass
