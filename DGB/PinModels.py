"""
BaseModel to handel the generic rest GPIO api calls to control.

Jeroen van Oosterhout, 30-01-2024
"""

from pydantic import BaseModel, model_validator, Field, RootModel
from typing import Literal, Union
from enum import Enum
from DGB.Tools import IOT_tools


class PinType(str, Enum):
    pinin = "in"
    pinout = "out"
    pincount = "count"
    pinnwayout = "nwayout"


def is_pin_type(ptype):
    try:
        PinType(ptype)
    except ValueError:
        return False
    return True


class PinIn(BaseModel):
    pin: int = Field(description="GPIO pin to configure, change or read")
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
        if self.pin not in range(29):
            raise ValueError(
                f"{self.pin} is not a valid GPIO pin number. Pin must be in range(27)"
            )
        if self.ptype is not PinType.pinin.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        return self


class PinOut(BaseModel):
    pin: int = Field(description="GPIO pin to configure, change or read")
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
    value: int | None = Field(
        default=None,
        description="The output value of the pin that is currently desired.",
    )
    password: str | None = Field(
        default=None,
        description="An optional safety layer to prevent unwanted activation of a pin. ATTENTION! Do not use your daily passwords for (online) accounts as this api has no https and no encription.",
    )
    blink: int | None = Field(
        default=None,
        description="The blink time of the output once for this number of seconds. Note it uses the previous set value to start from, the value of this call will be ignored.",
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if self.pin not in range(29):
            raise ValueError(
                f"{self.pin} is not a valid GPIO pin number. Pin must be in range(27)"
            )
        if self.ptype is not PinType.pinout.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        if self.initial not in [1, 0]:
            raise ValueError(
                f"{self.initial} is not a valid number. Initial must be either 1 or 0"
            )
        if self.value is not None:
            if self.value not in [1, 0]:
                raise ValueError(
                    f"{self.value} is not a valid number. Value must be either 1 or 0"
                )
        else:
            self.value = self.initial
        if self.blink is not None:
            if self.blink <= 0:
                raise ValueError(
                    f"{self.blink} is not a valid number. Blink must be larger >0"
                )
        if self.password is None:
            self.password = ""
        return self


class PinNWayOut(BaseModel):
    pin: int = Field(
        description="GPIO pin to configure, change or read. For the n way out type this is the pin with which the configuration is identified. This pin should also be listed in pin_list."
    )
    pin_list: list[int] = Field(
        description='List of >=2 GPIO pins to configure, change or read. The "pin" must also be in this lis. The list can include multiple "dummy" pins indicated bij -1. Pins can be aranged in any order.'
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

    active_pin: int | str | None = Field(
        default=None,
        description="The pin that must be turned on, indicated either as the pin number (int) or a pin_name (str). All other pins will be deactivated, all will be deactivated when set to -1.",
    )
    password: str | None = Field(
        default=None,
        description="An optional safety layer to prevent unwanted activation of a pin, only checked for the first pin in the list but applies to all pins. ATTENTION! Do not use your daily passwords for (online) accounts as this api has no https and no encription.",
    )
    # blink: int | None = Field(default= None, description='The blink time of the output once for this number of seconds. Note it uses the initial set value to start from.')

    @model_validator(mode="after")
    def validate_atts(self):
        if self.pin not in range(29):
            raise ValueError(
                f"{self.pin} is not a valid GPIO pin number. Pin must be in range(27)"
            )
        if not len(self.pin_list) >= 2:
            raise ValueError(f"{self.pin_list} is not a list of at least 2 GPIO pins")
        if self.initial == [0]:
            self.initial = [0] * len(self.pin_list)
        if self.active_state == [False]:
            self.active_state = [False] * len(self.pin_list)
        if self.pin_names == [""]:
            self.pin_names = [""] * len(self.pin_list)
        if self.password is None:
            self.password = ""

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
            if not self.pin_names[i] == "":
                for j in range(len(self.pin_names)):
                    if not i == j:
                        if self.pin_names[i] == self.pin_names[j]:
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

        if self.active_pin is not None:
            if self.active_pin not in self.pin_names:
                if IOT_tools.is_int(self.active_pin):
                    self.active_pin = int(self.active_pin)
                else:
                    raise ValueError(
                        f"Active_pin {self.active_pin} is neither in the pin list nor an int."
                    )
                if self.active_pin not in self.pin_list:
                    raise ValueError(
                        f"Active_pin {self.active_pin} is neither in the pin list nor in the pin_names list."
                    )
        return self


class PinCount(BaseModel):
    pin: int = Field(description="GPIO pin to configure, change or read")
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
    webhook: str | None = Field(
        default=None,
        description="Endpoint in Home assistant to send state changes to at the moment they occure.",
    )

    @model_validator(mode="after")
    def validate_atts(self):
        if self.pin not in range(29):
            raise ValueError(
                f"{self.pin} is not a valid GPIO pin number. Pin must be in range(27)"
            )
        if self.ptype is not PinType.pincount.value:
            raise ValueError(
                f"{self.ptype} is not a valid pin configuration. Please leave this value empty in the configuration."
            )
        return self


class PinModel(RootModel):
    root: Union[PinIn, PinOut, PinCount, PinNWayOut] = Field(..., discriminator="ptype")

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
