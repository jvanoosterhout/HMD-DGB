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

        self.rate = 0
        self.last_changed = time.monotonic()
        self.pw = {}
        self.HASS_interface = None
        self.dgb_context = dgb_context

        self.label = f"{self.config.unique_id} (GPIO {self.config.pin})"
        self.logger = logging.getLogger(f"pin_{self.config.pin}")
        self.logger.info(f"Configuring pin {self.label}.")
        logging.getLogger().setLevel(logging.INFO)

    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """

    def on(self, **kwargs) -> bool:
        return False

    def off(self, **kwargs) -> bool:
        return False

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device.
        """

    def update(self):
        pass
