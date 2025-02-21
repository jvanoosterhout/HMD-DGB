#!/usr/bin/env python
# encoding: utf-8
"""
Generic rest api to control Raspberry GPIO pins from Home Assistant. Including fallback option when iether of the two reboots. 

Jeroen van Oosterhout, 30-01-2024
"""

from fastapi import FastAPI, Request, HTTPException, Depends, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from typing import Optional, Union
import uvicorn
import logging
import time
import psutil
from gpiozero import CPUTemperature
from PinAPI.PinKeeper import PinKeeper
from PinAPI.PinModels import *

logging.basicConfig(level='INFO')

class Pin_api:
    def __init__(self, name:str, api_url:str="http://IP-ADRES:8123/api/", token:str="secret", pin_pw_list:dict={}):
        self.name = name
        self.pin_maker = PinKeeper(api_url=api_url, token=token, pin_pw_list=pin_pw_list)
        self.logger = logging.getLogger("{}_log".format(self.name))
        self.logger.info('starting {}'.format(self.name))
        self.base_url = "/api/v1/"
        self.app = FastAPI()
        # Start and run controller
        # @asynccontextmanager
        # async def lifespan(app: FastAPI):
        #     for callback in parallel_loop_cbs: 
        #         if callback is not None: 
        #             asyncio.create_task(callback())
        #     yield

        # self.app = FastAPI(lifespan=lifespan)

        @self.app.get(self.base_url + 'sys/info')
        def krijg_staat(request: Request):
            """
                This endpoint returns basic system information on the host like CPU temperature (celcius), up time (hours), cpu temperature and memory usage. 
            """
            cpu_temp = CPUTemperature().temperature
            up_time = time.monotonic()/60/60
            cpu_percentage = psutil.cpu_percent(interval=1)
            memory_usage = psutil.virtual_memory().percent
            return self.jsonify({"is_active": "True","cpu_temp": cpu_temp, "up_time": up_time, "cpu_percentage": cpu_percentage, "memory_usage": memory_usage })
        

        @self.app.post(self.base_url + 'pin/{pin_type}')
        async def post_pin(pin_type: PinType, 
                          pin_config = Body(openapi_examples={"in": { 
                                                                    "value": {
                                                                        "pin": "1",
                                                                        "active_state": 1, 
                                                                        "pull_up": 1,
                                                                        "webhook": "my_home_assisistant_pin_in_1"
                                                                        },
                                                                    },
                                                                "out": {
                                                                    "value": {
                                                                        "pin": "1",
                                                                        "initial": 0,
                                                                        "active_state": 1,
                                                                        "value": 1,
                                                                        "password": "secret",
                                                                        "blink": 1
                                                                        }, 
                                                                    },
                                                                "count": {
                                                                    "value": {
                                                                            "pin": "1",
                                                                            "active_state": 1,
                                                                            "pull_up": 1,
                                                                            "webhook": "my_home_assisistant_pin_count_1"
                                                                    },
                                                                },
                                                            },
                                                        )): 
            """
                This endpoint allows to create new pins or change the state of an output type pin device. 
            """
            pin_config['ptype'] = pin_type.value
            try:
                pin_model = Pin(pin_config)
            except ValidationError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # pin_config_dict = pin_model.model_dump() 
            
            self.logger.info('Posting new (value for) pin: {}'.format(pin_model))
            if self.pin_maker.SetPin(pin_model): 
                return self.jsonify(self.pin_maker.GetPin(pin_model))    


        @self.app.get(self.base_url + 'pin/{pin_type}')
        async def get_pin(pin_type: PinType, 
                          pin_config_in: Optional[PinIn] = Depends(PinIn),
                          pin_config_out: Optional[PinOut] = Depends(PinOut),
                          pin_config_count: Optional[PinCount] = Depends(PinCount)): 
            """
                This endpoint allows to retrieve the curent pin state of the specified existin pin. 
                Mind that the configuration of the pin must match the saved configuration. In case 
                the pin does not exist (due to e.g. reboot), the pin is created according to the 
                configuration, like it was a POST.
            """
            if pin_type == PinType.pinin and isinstance(pin_config_in, PinIn):
                pin_model = Pin(pin_config_in.model_dump())
            elif pin_type == PinType.pinout and isinstance(pin_config_out, PinOut):
                pin_model = Pin(pin_config_out.model_dump())
            elif pin_type == PinType.pincount and isinstance(pin_config_count, PinCount):
                pin_model = Pin(pin_config_count.model_dump())
            else:
                raise HTTPException(status_code=400, detail="Invalid pin configuration for the given pin type")
            
            self.logger.info('Getting value of pin: {}'.format(pin_model))
            ret = self.pin_maker.GetPin(pin_model)
            if type(ret) == bool: 
                return self.jsonify(pin_model.root.model_dump())
            else:
                return self.jsonify(ret)
            

        self.logger.info('{} started'.format(self.name))


    def jsonify(self, json_dict):
        return JSONResponse(content=jsonable_encoder(json_dict))
    

# if __name__ == "__main__":
#     pin_api = Pin_api(name = "pin api")
#     uvicorn.run(pin_api.app, host='IP-ADRES', port=11411)

    # pin out = 25
    #pin in = 16