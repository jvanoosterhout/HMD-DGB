#!/usr/bin/env python
# encoding: utf-8
"""
Binder to manage actions to execute on specific triggers. 
The triggers are asumed to originate from a device or pin, which hold the binder. 
The binder keeps a list of actions (references to functions of the target device) 
that wil execute when a specific trigger/callback of holding device fires. 
This means that one device has multple binders: one per trigger.

Jeroen van Oosterhout, 24-01-2026
"""
import logging
# dynamic_rules.py
from durable.lang import ruleset, when_all, when_any, m, any, all, post, get_host, get_state  # Durable Python DSL
# import yaml
import json
from typing import Any, Dict, Callable
from PinAPI.DataStore import DataStore

class pintest():
    def __init__(self, id: str):
        self.id = id

    def on(self, t="-" ):
        print("{} is on with t={}".format(self.id, t.m))

    def off(self, t="-" ):
        print("{} is off with t={}".format(self.id, t.m))

class Binder:
    def __init__(self, datastore: DataStore):
        self.logger = logging.getLogger("Binder")
        self.datastore = datastore


    def new_binding(self, bind: dict):
        if "with" in bind and "rulesets" in bind:
            if "ruleset_name" in bind:
                ruleset_name = bind["ruleset_name"]
            else:                
                ruleset_name = "ruleset_{}".format(len(self.datastore.bindings))

            if self.devices_and_calls_exist(bind):
            
                self.logger.info("creating binding '{}' with ruleset: {}".format(ruleset_name, bind["rulesets"]))
                self.set_rule(ruleset_name, bind["rulesets"])
                self.datastore.add_binding(bind["with"], ruleset_name)
            else:
                self.logger.warning("Invalid binding configuration, device(s) or call(s) not found for: {}".format(bind))
        else:
            self.logger.warning("Invalid binding configuration, missing 'with' or 'rulesets' key: {}".format(bind))

    def set_rule(self, ruleset_name: str, rules: dict):
        with ruleset(ruleset_name): 
            for rule_name, rule_def in rules.items(): 
                print("building rule: {}".format(rule_name))
                condition = self.build_condition(rule_def.get("when").get("all"))
                # action_name = rule_def.get("run") 
                # self.logger.info(self.datastore.get_functions(rule_def.get("run").get("id")))
                # Create the rule dynamically 
                @when_all(condition)
                def custom_function(c): 
                    # Look up the Python function by name 
                    # self.logger.info("run {}".format(c.m["value"]))
                    for rule_name, rule_def in rules.items():
                        if rule_def.get("when").get("all").get("m").get("value") == c.m["value"]:
                            # call function and send the posted event
                            # self.logger.info(rule_def.get("run").get("id"))
                            # self.logger.info(self.datastore.get_functions(rule_def.get("run").get("id")))
                            self.logger.info("triggering action {} of device {}".format(rule_def.get("run").get("call"), rule_def.get("run").get("id")))
                            self.datastore.get_functions(rule_def.get("run").get("id")).get(rule_def.get("run").get("call"))()
                            return
                    self.logger.warning("failed to trigger action for {}".format(c.m))
                    
    def build_condition(self, dict_rule: dict):
        # {"m": {"type": "greeting"}}
        if "m" in dict_rule:
            # print("building condition: {}".format(dict_rule))
            expr = None
            for key, value in dict_rule["m"].items():
                part = getattr(m, key) == value
                # print(part.value)
                expr = part if expr is None else expr & part
                # print(expr)
            return expr

        # {"all": [ ... ]}
        # if "all" in dict_rule:
        #     print("building condition for all: {}".format(dict_rule["all"]))
        #     return all(self.build_condition(dict_rule["all"]) )

        # # {"any": [ ... ]}
        # if "any" in dict_rule:
        #     return any(self.build_condition(x) for x in dict_rule["any"])

        raise ValueError("Unsupported condition format")

    def devices_and_calls_exist(self, bind: dict) -> bool:
        if bind["with"] not in self.datastore.devices_objects and bind["with"] not in self.datastore.pins_objects:
            self.logger.warning("Device '{}' not found in datastore for binding: {}".format(bind["with"], bind))
            return False
        for rule_name, rule_def in bind["rulesets"].items():
            if "run" not in rule_def:
                self.logger.warning("Missing 'run' definition in rule '{}' of ruleset '{}'".format(rule_name, rule_def))
                return False
            
            run_def = rule_def["run"]
            if "id" not in run_def or "call" not in run_def:
                self.logger.warning("Missing 'id' or 'call' in 'run' definition of rule '{}' of ruleset '{}'".format(rule_name, run_def))
                return False
            
            device_id = run_def.get("id")
            functions = self.datastore.get_functions(device_id)
            if not functions:
                self.logger.warning("Device '{}' not found in datastore for rule '{}' of ruleset '{}'".format(device_id, rule_name, run_def))
                return False
            
            call_name = run_def.get("call")
            if call_name not in functions:
                self.logger.warning("Call '{}' not found for device '{}' in datastore for rule '{}' of ruleset '{}'".format(call_name, device_id, rule_name, run_def))
                return False
        return True
    

if __name__ == "__main__":
    b = Binder()
    pt1 = pintest("pin1")
    pt2 = pintest("pin2")
    object_registry: Dict[str, Any] = {}
    object_registry["pin1"] = pt1.on
    object_registry["pin2"] = pt1.off
    
    rul_spec2 = {
            "p_on": {
                "when": {
                    "all": 
                    { "m": { "value": "on" } }
                    
                },
                "run": "pin2"
            },
            "p_off": {
                "when": {
                    "all": 
                    { "m": {"value": "off" } }
                    
                },
                "run": "pin1"
            }
    }
    b.set_rule("test1",    rul_spec2, object_registry)
    rul_spec2 = {
            "p_on": {
                "when": {
                    "all": 
                    { "m": {  "value": "on" } }
                    
                },
                "run": "pin2"
            },
            "p_off": {
                "when": {
                    "all": 
                    { "m": {  "value": "off" } }
                    
                },
                "run": "pin1"
            }
    }
    b.set_rule("test2",    rul_spec2, object_registry)
    print(get_host().get_ruleset("test1").get_definition())
    print(get_host().get_ruleset("test2").get_definition())
    post("test1", { "value": "on"})
    post("test1", { "value": "off", "x": "y"})

