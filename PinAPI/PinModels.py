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
            pin = self.pin 
            ptype = self.ptype  
            active_state = self.active_state 
            pull_up= self.pull_up
            webhook = self.webhook
            
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if ptype is not PinType.pinin.value: 
                raise ValueError(f'{ptype} is not a valid pin configuration.')
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
            pin = self.pin 
            ptype = self.ptype  
            initial = self.initial 
            value = self.value
            blink = self.blink
            password = self.password
            
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if ptype is not PinType.pinout.value: 
                raise ValueError(f'{ptype} is not a valid pin configuration.')
            if initial not in [ 1, 0]:
                raise ValueError(f'{initial} is not a valid number.')
            if value is not None: 
                if value not in [ 1, 0]:
                    raise ValueError(f'{value} is not a valid number.')
            else:
                self.value = initial 
            if blink is not None:
                if blink < 0: 
                    raise ValueError(f'{blink} is not a valid number.')
            return self

class PinCount(BaseModel):
        pin: int  
        ptype: Literal[PinType.pincount.value] = PinType.pincount.value
        active_state: bool = True 
        pull_up: bool = True 
        webhook: str | None = None
        
        @model_validator(mode='after')
        def validate_atts(self):
            pin = self.pin 
            ptype = self.ptype  
            webhook = self.webhook
            
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if ptype is not PinType.pincount.value: 
                raise ValueError(f'{ptype} is not a valid pin configuration.')
            return self
        

class Pin(RootModel):
    root: Union[PinIn, PinOut, PinCount] = Field(..., discriminator='ptype')

