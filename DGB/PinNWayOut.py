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
from DGB.PinModels import PinModel, PinType
from DGB.PinOut import Pin_out


class Pin_N_way_out(Pin):
    def __init__(self, config: PinModel, dgb_context: DGBContext):
        """
        Initialiseer the Pin_N_way_out class.

        Parameters:
        config (Pin rootmodel): the pin configuration.
        """
        super().__init__(config=config, dgb_context=dgb_context)
        self.Pins: list[Pin_out] = []
        self.active_pin: int | str | None = None

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

    def GetPinIndex(self, active_pin: int | str) -> int:
        n = -1
        if isinstance(active_pin, str) and active_pin in self.config.pin_names:
            n = self.config.pin_names.index(active_pin)
        if isinstance(active_pin, int) and active_pin in self.config.pin_list:
            n = self.config.pin_list.index(active_pin)
        return n

    def GenerateSubPinConfig(self, n: int) -> PinModel:
        return PinModel(
            {
                "pin": self.config.pin_list[n],
                "unique_id": f"{self.config.unique_id}_{n}",
                "ptype": PinType.pinout.value,
                "initial": self.config.initial[n],
                "active_state": self.config.active_state[n],
            }
        )

    def on(self, active_pin: int | str) -> bool:
        self.off()

        if active_pin is None:
            self.active_pin = None
            return True
        n = self.GetPinIndex(active_pin)

        if n == -1:
            return False
        if self.config.pin_list[n] == -1:
            self.logger.info(
                f'N Way Out dummy pin with name "{self.config.pin_names[n]}" turned on'
            )
            self.active_pin = active_pin
            return True

        if self.config.pin_list[n] != self.config.pin:
            for p in self.Pins:
                if p.config.pin == self.config.pin_list[n]:
                    p.on(is_PinNWayOut=True)
        else:
            self.pin_device.on()

        self.logger.info(
            f'N Way Out pin {self.config.pin_list[n]} with name "{self.config.pin_names[n]}" turned on'
        )

        self.active_pin = active_pin

        self.persist_action(
            {
                "args": [
                    {"name": "active_pin", "value": active_pin},
                ]
            }
        )

        return True

    def off(self) -> bool:
        for p in self.Pins:
            p.off(is_PinNWayOut=True)
        self.pin_device.off()
        self.persist_action(
            {
                "args": [
                    {"name": "active_pin", "value": None},
                ]
            }
        )
        self.logger.info("All N Way Out pins turned off")
        return True

    def set_state(self, **states: int | str | None) -> bool:
        return all(
            self._set_state_value(state_name, state)
            for state_name, state in states.items()
        )

    def _set_state_value(self, state_name: str, state: int | str | None) -> bool:
        if state_name not in {"active_pin"}:
            self.logger.warning(
                "pin %s unsupported state name %r", self.label, state_name
            )
            return False

        return self.off() if state is None else self.on(active_pin=state)

    def persist_action(self, args):
        if self.dgb_context.is_action_persisted(self.config.unique_id):
            self.dgb_context.persist_action(self.config.unique_id, "set_state", args)
