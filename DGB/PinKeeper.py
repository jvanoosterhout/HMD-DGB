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
#    Pin keeper class to create and manage all pins

import logging

from DGB.DGBContext import DGBContext, DuplicatePolicy
from DGB.Pin import Pin
from DGB.PinCount import Pin_count
from DGB.PinIn import Pin_in
from DGB.PinModels import PinModel, PinType
from DGB.PinNWayOut import Pin_N_way_out
from DGB.PinOut import Pin_out


class PinKeeper:
    def __init__(
        self,
        dgb_context: DGBContext,
    ):
        """
        Initialize the PinKeeper class with default values.
        """
        self.logger = logging.getLogger("PinKeeper")
        self.dgb_context = dgb_context
        logging.getLogger().setLevel(logging.INFO)

        self.logger.info("PinKeeper initialized.")

    def __del__(self):
        for pin in self._pins():
            for sub_pin in getattr(pin, "Pins", []):
                sub_pin.pin_device.close()
            pin.pin_device.close()
        self.logger.info("PinKeeper cleaned up all pins")

    def _pins(self) -> list[Pin]:
        """Return all pin objects registered in the DGB context."""
        return [
            obj.dgb_obj
            for obj in self.dgb_context.DGB_objects.values()
            if isinstance(obj.dgb_obj, Pin)
        ]

    def SetPin(
        self, config: PinModel, policy: DuplicatePolicy = DuplicatePolicy.SKIP
    ) -> bool:
        """
        Create a new pin, unless its unique_id or one of its GPIO pins is already in use.

        Parameters:
        config (Pin): Configuratie van de pin.
        policy (DuplicatePolicy): Policy applied when the unique_id already exists.

        Returns:
        bool: True if succesfully made, otherwise False.
        """
        if not self._handle_existing_pin(config.unique_id, policy):
            return False

        gpios = (
            config.pin_list
            if config.ptype == PinType.pinnwayout.value
            else [config.pin]
        )
        for gpio in gpios:
            if gpio >= 0 and self._gpio_in_use(gpio):
                self.logger.warning(
                    f"GPIO {gpio} of pin {config.unique_id} is already in use -- skipping"
                )
                return False

        if self.MakeNewPin(config):
            return True
        self.logger.warning("No pin configuration recognized.")
        return False

    def _handle_existing_pin(
        self,
        unique_id: str,
        policy: DuplicatePolicy,
    ) -> bool:
        """
        Check whether an object with this unique_id already exists and apply policy.

        Returns:
            True  -> caller may proceed with creating the pin
            False -> caller must skip
        """
        if not self.dgb_context.is_registered(unique_id):
            return True

        if policy == DuplicatePolicy.SKIP:
            self.logger.warning(
                f"Pin with unique_id '{unique_id}' already exists -- skipping"
            )
            return False

        self.logger.warning(
            f"Pin with unique_id '{unique_id}' already exists -- unknown policy '{policy}', skipping"
        )
        return False

    def _gpio_in_use(self, gpio: int) -> bool:
        """
        Check if a GPIO pin is already used by a registered pin.

        Parameters:
        gpio (int): GPIO pin number.

        Returns:
        bool: True if the GPIO pin is in use, otherwise False.
        """
        for pin in self._pins():
            if pin.config.pin == gpio:
                return True
            if (
                pin.config.ptype == PinType.pinnwayout.value
                and gpio in pin.config.pin_list
            ):
                return True
        return False

    def MakeNewPin(self, config: PinModel) -> bool:
        """
        Create a new pin based on the configuration optained from the rest call

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        bool: True if succesfully made, otherwise False.
        """
        self.logger.info(f"Make a new pin with config: {config}")
        if config.ptype is PinType.pinout.value:
            P = Pin_out(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(
                config.unique_id,
                P,
                {
                    "on": P.on,
                    "off": P.off,
                    "blink": P.blink,
                    "set_state": P.set_state,
                },
            )
        elif config.ptype is PinType.pinin.value:
            P = Pin_in(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(config.unique_id, P)
        elif config.ptype is PinType.pincount.value:
            P = Pin_count(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(config.unique_id, P, {"set_state": P.set_state})
        elif config.ptype is PinType.pinnwayout.value:
            P = Pin_N_way_out(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(
                config.unique_id,
                P,
                {
                    "on": P.on,
                    "off": P.off,
                    "set_state": P.set_state,
                },
            )
            for lst in range(len(config.pin_list)):
                if config.pin_list[lst] != config.pin and config.pin_list[lst] >= 0:
                    sub_config = P.GenerateSubPinConfig(lst)
                    self.logger.info(f"Configure sub pin {sub_config}.")
                    N = Pin_out(
                        config=sub_config,
                        is_PinNWayOut=True,
                        dgb_context=self.dgb_context,
                    )
                    N.ConfigurePin()
                    P.Pins.append(N)
        else:
            return False
        P.ConfigurePin()
        self.logger.info(f"Pin {P.label} added.")
        return True
