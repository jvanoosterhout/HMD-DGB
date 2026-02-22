import logging

class DataStore:
    def __init__(self):
        self.devices_functions : dict[str, dict[str,callable]] = {}   # str -> list of callables
        self.devices_objects : dict[str, any]= {}                           # str -> device object
        self.pins_functions : dict[str, dict[str,callable]] = {}      # str -> list of callables
        self.pins_objects : dict[str, any] = {}                             # str -> pin object
        self.bindings : dict[str, list[str]] = {}                           # str -> list of ruleset_names
        self.logger = logging.getLogger("DataStore")
        self.logger.info('DataStore initialized.')
    
    def add_device(self, unique_id:str, device_obj:any, functions:dict[str, callable]|None=None):
        self.devices_objects[unique_id] = device_obj
        self.devices_functions[unique_id] = functions or {}
        self.logger.info("added device {} with functions {}".format(unique_id, functions if functions else []))
    
    def add_pin(self, unique_id:str, pin_obj:any, functions:dict[str, callable]|None=None):
        self.pins_objects[unique_id] = pin_obj
        self.pins_functions[unique_id] = functions or {}
        self.logger.info("added pin {} with functions {}".format(unique_id, functions if functions else []))
    
    def add_binding(self, device_id:str, ruleset_name:str, has_timeout:bool=False):
        if device_id not in self.bindings:
            self.bindings[device_id] = []
        self.bindings[device_id].append({"name": ruleset_name, "timeout": has_timeout})
        self.logger.info("added binding for device {} to ruleset {}".format(device_id, ruleset_name))
    
    def get_device(self, unique_id:str):
        return self.devices_objects.get(unique_id)
    
    def get_pin(self, unique_id:str):
        return self.pins_objects.get(unique_id)
    
    def get_functions(self, unique_id:str) -> dict[str, callable]: 
        # print(self.devices_functions)
        # print(self.pins_functions)

        if unique_id in self.devices_functions:
            return self.devices_functions.get(unique_id)
        if unique_id in self.pins_functions:
            return self.pins_functions.get(unique_id)
        return {}
    
    def get_bindings(self, device_id:str):
        return self.bindings.get(device_id, [])