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
#    BaseModel to handel the generic rest GPIO api calls to control.

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, RootModel, model_validator

UNIQUE_ID_PATTERN = re.compile(r"[a-z0-9_-]+")


class PinType(str, Enum):
    pinin = "in"
    pinout = "out"
    pincount = "count"
    pinnwayout = "nwayout"


class PinBase(BaseModel):
    pin: int = Field(description="GPIO pin to configure, change or read")
    unique_id: str = Field(
        description="Unique identifier of the pin, used to address it in bindings, events, state_initialization and retained-action topics. Allowed characters: [a-z0-9_-].",
    )

    @model_validator(mode="after")
    def validate_unique_id(self):
        if self.pin not in range(29):
            raise ValueError(
                f"{self.pin} is not a valid GPIO pin number. Pin must be in range(27)"
            )
        if not self.unique_id:
            raise ValueError("unique_id must be a non-empty str")
        if not UNIQUE_ID_PATTERN.fullmatch(self.unique_id):
            raise ValueError(
                f"unique_id {self.unique_id!r} is invalid. Only lowercase letters, digits, '_' and '-' are allowed."
            )
        return self


class PinIn(PinBase):
    ptype: Literal[PinType.pinin.value] = Field(
        default=PinType.pinin.value,
        description="The functional type of the pin like in(put) or out(put).",
    )
    active_state: bool = Field(
        default=True,
        description="If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed",
    )
    pull_up: bool = Field(
        default=True,
        description="If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.",
    )
    webhook: str | None = Field(
        default=None,
        description="Endpoint in Home assistant to send state changes to at the moment they occure.",
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if self.ptype is not PinType.pinin.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        return self


class PinOut(PinBase):
    ptype: Literal[PinType.pinout.value] = Field(
        default=PinType.pinout.value,
        description="The functional type of the pin like in(put) or out(put).",
    )
    initial: int = Field(
        default=0,
        description="The initial output value of the pin at the time it is created.",
    )
    active_state: bool = Field(
        default=False,
        description="If True, when the software state is HIGH, the hardware pin is HIGH. If False, the hardware output is reversed",
    )

    blink: int | None = Field(
        default=None,
        description="Default blink time in seconds, used by the blink call when no blink time is provided.",
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if self.ptype is not PinType.pinout.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        if self.initial not in [1, 0]:
            raise ValueError(
                f"{self.initial} is not a valid number. Initial must be either 1 or 0"
            )
        if self.blink is not None and self.blink <= 0:
            raise ValueError(f"{self.blink} is not a valid number. Blink must be >0")
        return self


class PinNWayOut(PinBase):
    pin: int = Field(
        description="GPIO pin to configure, change or read. For the n way out type this is the pin with which the configuration is identified. This pin must also be listed in pin_list."
    )
    pin_list: list[int] = Field(
        description='List of >=2 unique GPIO pins to configure, change or read. The "pin" must also be in this list. The list can include multiple "dummy" pins indicated by -1. Pins can be aranged in any order.'
    )
    ptype: Literal[PinType.pinnwayout.value] = Field(
        default=PinType.pinnwayout.value,
        description="The functional type of the pin like in(put) or out(put).",
    )
    initial: list[int] = Field(
        default=[0],
        description='List initial output values of the pins at the time they are created, the order of initial should match the order in pin. At most one pin can be high, this can also be the/a "dummy" pin.',
    )
    active_state: list[bool] = Field(
        default=[False],
        description="List of states, the order of active_state should match the order in pin. If True, when the software state is HIGH, the hardware pin is HIGH. If False, the hardware output is reversed",
    )
    pin_names: list[str] = Field(
        default=[""],
        description='List of names to identify the pins, the order of names should match the order in pin. This could be ["open", "close", "stop"] or ["0", "1", "2", "3]". ',
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if not len(self.pin_list) >= 2:
            raise ValueError(f"{self.pin_list} is not a list of at least 2 GPIO pins")
        if self.initial == [0]:
            self.initial = [0] * len(self.pin_list)

        if self.pin not in self.pin_list:
            raise ValueError(f"Pin {self.pin} must also be listed in pin_list.")
        real_pins = [p for p in self.pin_list if p != -1]
        if len(real_pins) != len(set(real_pins)):
            raise ValueError(
                f"{self.pin_list} contains duplicate GPIO pins. Only the dummy pin -1 may be repeated."
            )
        if self.active_state == [False]:
            self.active_state = [False] * len(self.pin_list)
        if self.pin_names == [""]:
            self.pin_names = [""] * len(self.pin_list)

        if not len(self.pin_list) == len(self.initial):
            raise ValueError(
                'the "initial" list does not match the length of the pin_list'
            )
        if not len(self.pin_list) == len(self.active_state):
            raise ValueError(
                'the "active_state" list does not match the length of the pin_list'
            )
        if not len(self.pin_list) == len(self.pin_names):
            raise ValueError(
                'the "pin_names" list does not match the length of the pin_list'
            )

        for i in range(len(self.pin_list)):
            if self.pin_list[i] not in range(-1, 29):
                raise ValueError(
                    f"The {i}th pin {self.pin_list[i]} is not a valid GPIO pin number. Pin must be in range(27) or a dummy as -1."
                )
            if self.initial[i] not in [1, 0]:
                raise ValueError(
                    f"The {i}th initial {self.initial[i]} is not a valid number. Initial must be either 1 or 0"
                )
            if self.pin_names[i] != "":
                for j in range(len(self.pin_names)):
                    if i != j and self.pin_names[i] == self.pin_names[j]:
                        raise ValueError(
                            f"The {i}th pin_names has an identical name as the {j}th name. All should be empty or unique."
                        )
            if self.initial[i] not in [1, 0]:
                raise ValueError(
                    f"The {i}th initial {self.initial[i]} is not a valid number. Initial must be either 1 or 0"
                )

        if self.ptype is not PinType.pinnwayout.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        return self


class PinCount(PinBase):
    ptype: Literal[PinType.pincount.value] = Field(
        default=PinType.pincount.value,
        description="The functional type of the pin like in(put) or out(put).",
    )
    active_state: bool = Field(
        default=True,
        description="If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed",
    )
    pull_up: bool = Field(
        default=False,
        description="If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.",
    )
    when_activated: bool = Field(
        default=True,
        description="If True, count pulses on the rising edge (when the input becomes active).",
    )
    when_deactivated: bool = Field(
        default=True,
        description="If True, count pulses on the falling edge (when the input becomes inactive).",
    )
    scaling_factor: float = Field(
        default=1.0,
        description="Scale factor for reported totals. Reported count is count_total / scaling_factor.",
    )
    webhook: str | None = Field(
        default=None,
        description="Endpoint in Home assistant to send state changes to at the moment they occure.",
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if self.ptype is not PinType.pincount.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        if self.scaling_factor <= 0:
            raise ValueError(
                f"{self.scaling_factor} is not valid. scaling_factor must be > 0"
            )
        return self


class PinModel(RootModel):
    root: PinIn | PinOut | PinCount | PinNWayOut = Field(..., discriminator="ptype")

    def __getattr__(self, name: str) -> any:
        """_summary_

        # Without __getattr__
        Pin(...).root.pin   # Ok
        Pin(...).pin        # Error

        # With __getattr__
        Pin(...).root.pin   # Ok
        Pin(...).pin        # Ok

        Args:
            name (str): _description_

        Returns:
            any: _description_
        """
        return getattr(self.root, name)

    def __setattr__(self, name: str, value: any):
        """_summary_

        # Without __getattr__
        Pin(...).root.pin = x   # Ok
        Pin(...).pin = x        # Error

        # With __getattr__
        Pin(...).root.pin = x   # Ok
        Pin(...).pin = x        # Ok

        Args:
            name (str): _description_
            value (any): _description_
        """
        object.__setattr__(self.root, name, value)
