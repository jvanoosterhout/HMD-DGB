"""
BaseModel to handel the generic rest GPIO api calls to control. 

Jeroen van Oosterhout, 30-01-2024
"""

from pydantic import BaseModel, model_validator, Field
from enum import Enum

class PinType(str, Enum):
    pinin = "in"
    pinout = "out"
    pincount = "count"

def is_pin_type(type):
    try:
        PinType(type)
    except ValueError:
        return False
    return True

class PinIn(BaseModel):
        pin: int  = Field(description='GPIO pin to configure')
        type: str = Field(default= "in", description='The function type of the pin like in(put) or out(put).')
        active_state: bool = Field(default= True, description='If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed')
        pull_up: bool = Field(default= True, description='If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.')
        webhook: str | None = Field(default= None, description='Endpoint in Home assistant to send state changes to at the moment they occure')
        
        model_config = {
            "json_schema_extra": {
                "example": [{
                        "pin": "1",
                        "active_state": 1, 
                        "pull_up": 1,
                        "webhook": "my_home_assisistant_pin_in_1"
                },
                {
                        "pin": "1",
                        "initial": 0,
                        "active_state": 1,
                        "value": 1,
                        "password": "secret",
                        "blink": 1
                },
                {
                        "pin": "1",
                        "active_state": 1,
                        "pull_up": 1,
                        "webhook": "my_home_assisistant_pin_count_1"
                }]
            }
        }

        @model_validator(mode='after')
        def validate_atts(self):
            pin = self.pin 
            type = self.type  
            active_state = self.active_state 
            pull_up= self.pull_up
            webhook = self.webhook
            
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if type is not PinType.pinin.value: 
                raise ValueError(f'{type} is not a valid pin configuration.')
                    
            return self

class PinOut(BaseModel):
        pin: int  
        type: str = "out"  
        initial: int = 0
        active_state: bool = True 
        value: int  | None = None 
        password: str | None = None 
        blink: int | None = None        

        model_config = {
            "json_schema_extra": {
                "example": {
                        "pin": "1",
                        "initial": 0,
                        "active_state": 1,
                        "value": 1,
                        "password": "secret",
                        "blink": 1
                }
            }
        }
        @model_validator(mode='after')
        def validate_atts(self):
            pin = self.pin 
            type = self.type  
            initial = self.initial 
            value = self.value
            blink = self.blink
            password = self.password
            print('hoi')
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if type is not PinType.pinout.value: 
                raise ValueError(f'{type} is not a valid pin configuration.')
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
        type: str = "count"  
        active_state: bool = True 
        pull_up: bool = True 
        webhook: str | None = None
        
        model_config = {
            "json_schema_extra": {
                "example": {
                        "pin": "1",
                        "active_state": 1,
                        "pull_up": 1,
                        "webhook": "my_home_assisistant_pin_count_1"
                }
            }
        }
        @model_validator(mode='after')
        def validate_atts(self):
            pin = self.pin 
            type = self.type  
            webhook = self.webhook
            
            if pin not in range(27): 
                raise ValueError(f'{pin} is not a valid GPIO pin number.')
            if type is not PinType.pincount.value: 
                raise ValueError(f'{type} is not a valid pin configuration.')
                    
            return self