"""
BaseModel to handel the generic rest GPIO api calls to control. 

Jeroen van Oosterhout, 30-01-2024
"""

from pydantic import BaseModel, model_validator, Field, RootModel, ValidationError
from typing import Literal, Union
from enum import Enum

class PinType(str, Enum):
    pinin = "in"
    pinout = "out"
    pincount = "count"

def is_pin_type(ptype):
    try:
        PinType(ptype)
    except ValueError:
        return False
    return True

class PinIn(BaseModel):
        pin: int  = Field(description='GPIO pin to configure')
        ptype: Literal[PinType.pinin.value] = Field(default= PinType.pinin.value, description='The functional type of the pin like in(put) or out(put).')
        active_state: bool = Field(default= True, description='If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed')
        pull_up: bool = Field(default= True, description='If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.')
        webhook: str | None = Field(default= None, description='Endpoint in Home assistant to send state changes to at the moment they occure')
        
        @model_validator(mode='after')
        def validate_atts(self):            
            if self.pin not in range(27): 
                raise ValueError(f'{self.pin} is not a valid GPIO pin number. Pin must be in range(27)')
            if self.ptype is not PinType.pinin.value: 
                raise ValueError(f'{self.ptype} is not a valid pin configuration.')
            return self

class PinOut(BaseModel):
        pin: int  
        ptype: Literal[PinType.pinout.value] = PinType.pinout.value
        initial: int = 0
        active_state: bool = True 
        value: int  | None = None 
        password: str | None = None 
        blink: int | None = None        

        @model_validator(mode='after')
        def validate_atts(self):
            if self.pin not in range(27): 
                raise ValueError(f'{self.pin} is not a valid GPIO pin number. Pin must be in range(27)')
            if self.ptype is not PinType.pinout.value: 
                raise ValueError(f'{self.ptype} is not a valid pin configuration.')
            if self.initial not in [ 1, 0]:
                raise ValueError(f'{self.initial} is not a valid number. Initial must be either 1 or 0')
            if self.value is not None: 
                if self.value not in [ 1, 0]:
                    raise ValueError(f'{self.value} is not a valid number. Value must be either 1 or 0')
            else:
                self.value = self.initial 
            if self.blink is not None:
                if self.blink <= 0: 
                    raise ValueError(f'{self.blink} is not a valid number. Blink must be larger >0')
            if self.password is None:
                self.password = ""
            return self

class PinCount(BaseModel):
        pin: int  
        ptype: Literal[PinType.pincount.value] = PinType.pincount.value
        active_state: bool = True 
        pull_up: bool = True 
        webhook: str | None = None
        
        @model_validator(mode='after')
        def validate_atts(self):
            if self.pin not in range(27): 
                raise ValueError(f'{self.pin} is not a valid GPIO pin number. Pin must be in range(27)')
            if self.ptype is not PinType.pincount.value: 
                raise ValueError(f'{self.ptype} is not a valid pin configuration.')
            return self
        

class Pin(RootModel):
    root: Union[PinIn, PinOut, PinCount] = Field(..., discriminator='ptype')
    
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
    
    def __setattr__(self, name: str, value:any):
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


