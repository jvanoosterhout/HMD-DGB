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
import copy
import logging
# dynamic_rules.py
from durable.lang import ruleset, when_all, when_any, m, c, s, any, all, none, post, get_host, get_state, timeout, update_state, assert_fact, retract_fact, value  # Durable Python DSL
# import yaml
import json
from typing import Any, Dict, Callable
from PinAPI.DataStore import DataStore
import time

class pintest():
    def __init__(self, id: str):
        self.id = id

    def on(self, t="-" ):
        print("{} is on with t={}".format(self.id, t))
        return True

    def off(self, t="-" ):
        print("{} is off with t={}".format(self.id, t))
        return True

def post_event(unique_id, payload: dict, datastore: DataStore, logger: logging.Logger):
        for ruleset in datastore.get_bindings(unique_id):
            logger.info("posting event to ruleset {}: {}".format(ruleset["name"], payload))   
            rule_state = get_host().get_ruleset(ruleset["name"]).get_definition()
            if ruleset["timeout"]:
                assert_fact(ruleset["name"], payload) 
            else:          
                post(ruleset["name"], payload)    
            # post(ruleset["name"], payload)

            
        time.sleep(0.1)  # wait a bit for rules to process the event and set return_value in state
        time_out = 2
        succes_array = []
        for ruleset in datastore.get_bindings(unique_id):
            returend = False
            now = time.time()
            while not returend and (time.time() - now < time_out):
                rule_state = get_state(ruleset["name"])
                logger.info("state of ruleset {}: {}".format(ruleset["name"], rule_state))
                if 'return_value' in rule_state:
                    state = rule_state["return_value"]["value"] 
                    if state == "pending":
                         logger.info("rule {} is still pending, waiting...".format(ruleset["name"]))
                         time.sleep(0.5)
                         pass
                    returend = True
                    succes_array.append(state )
                    del rule_state["return_value"]
                    update_state(ruleset["name"], rule_state)  # clear return_value after reading
                time.sleep(0.5)  # wait a bit before checking again
            # if ruleset["timeout"]: #TODO: make function in separate thread, such that multiple events can be posted simultaneously without blocking each other, and timeouts can be handled more robustly
            #     retract_fact(ruleset["name"], payload)  # clean up the fact after processing
        
        logger.info("final state after posting to rulesets {}: {}".format(datastore.get_bindings(unique_id), succes_array))

def build_action(rules: dict, logger: logging.Logger, datastore: DataStore):
    def action(c): 
        # Look up the Python function by name 
        for rule_name, rule_def in rules.items():
            # identify the fired rule to find the right action to execute (in case of multiple rules in one ruleset)
            if not getattr(c.s, "value_store") is None:
                # logger.info(c.s)
                rule_identifier = c.s.value_store
                def_identifier = rule_def.get("when").get("all")[0].get("m")
            elif isinstance(rule_def.get("when").get("all"), list):
                def_identifier = rule_def.get("when").get("all")[0].get("m")  # assuming the first condition has a discriminative "value" field
                rule_identifier = c.first  # the value from the first event
            else:
                def_identifier = rule_def.get("when").get("all").get("m")  # assuming a single condition with "m"
                rule_identifier = c.m  # the value from the event
            logger.info("checking rule '{}' with condition value '{}' against event value '{}'".format(rule_name, def_identifier, rule_identifier))
            
            if def_identifier.get("value") == rule_identifier["value"]: 
                # call function and send the posted event
                logger.info("triggering action {} of device {}".format(rule_def.get("run").get("call"), rule_def.get("run").get("id")))
                action_function = datastore.get_functions(rule_def.get("run").get("id")).get(rule_def.get("run").get("call"))
                # todo: check if action fuction consumes arguments and call accordingly

                state = action_function()
                c.s.return_value = {"value": True if state is None or state else False}
                return 
            
        logger.warning("failed to trigger action for {}".format(c.m))
    
    return action


class Binder:
    def __init__(self, datastore: DataStore):
        self.logger = logging.getLogger("Binder")
        self.datastore = datastore
        self._BIND_NAMES = ["first", "second", "third", "fourth", "fifth", "sixth"]

    def new_binding(self, bind: dict):
        if "with" in bind and "rulesets" in bind:
            if "ruleset_name" in bind:
                ruleset_name = bind["ruleset_name"]
            else:                
                ruleset_name = "ruleset_{}".format(len(self.datastore.bindings))

            if self.devices_and_calls_exist(bind):
            
                self.logger.info("creating binding '{}' with ruleset: {}".format(ruleset_name, bind["rulesets"]))
                self.set_rule(ruleset_name, bind["rulesets"], bind["timeout"] if "timeout" in bind else 0)
                for dev in bind["with"]:
                    self.datastore.add_binding(dev, ruleset_name, True if "timeout" in bind and bind["timeout"] else False)
            else:
                self.logger.warning("Invalid binding configuration, device(s) or call(s) not found for: {}".format(bind))
        else:
            self.logger.warning("Invalid binding configuration, missing 'with' or 'rulesets' key: {}".format(bind))

    def set_rule(self, ruleset_name: str, rules: dict, timeout_sec: int = 0):
        with ruleset(ruleset_name): 
            all_condition_for_negate: list[value] = []
            for rule_name, rule_def in rules.items(): 
                self.logger.info("building rule: {}".format(rule_name))
                condition = self.build_condition(rule_def.get("when").get("all"))
                if isinstance(condition, list):
                    for cond in condition:
                        rebuilt_cond = value(vtype=cond._type, left=cond._left, op=cond._op, right=cond._right)
                        
                        print(rebuilt_cond.__dict__)
                        all_condition_for_negate.append(rebuilt_cond)
                else:
                    print(type(condition))
                    all_condition_for_negate.append(condition)
                
                action = build_action(rules, self.logger, self.datastore)
                               
                if isinstance(condition, list):
                    @when_all(*condition)
                    def action_handler(c):
                        self.logger.info("all conditions met, executing action")
                        c.s.return_value = {"value": "pending"}
                        action(c)
                        if timeout_sec > 0:
                            for cond in condition:
                                retract_fact(ruleset_name=ruleset_name, fact={"value": cond._right}) 

                    # if timeout_sec == 0:
                    #     @when_all(*condition)
                    #     def action_handler(c):
                    #         self.logger.info("all conditions met, executing action")
                    #         c.s.return_value = {"value": "pending"}
                    #         action(c)
                    # else:
                    #     assert_cond = None
                    #     for cond in condition:
                    #         plain_cond = value(vtype=cond._type, left=cond._left, op=cond._op, right=cond._right)
                    #         assert_cond = plain_cond if assert_cond is None else assert_cond & plain_cond
                    #     @when_all(assert_cond)
                    #     def action_handler(c):
                    #         self.logger.info("all conditions met, executing action")
                    #         c.s.return_value = {"value": "pending"}
                    #         action(c)
                
                else:
                    @when_all(condition)
                    def action_handler(c):
                        c.s.return_value = {"value": "pending"}
                        action(c)
                        # c.s.fired = True
                
            @when_all(+s.exception)
            def action_handler(c):
                self.logger.error("caught an exception: {}".format(c.s.exception))
                c.s.exception = None
            # all_cond = None
            # for cond in (all_condition_for_negate):
            #         print(type(cond))
            #         cond = none(cond)
            #         self.logger.info("condition for negate: {}".format(cond.__dict__))
            #         all_cond = (cond) if all_cond is None else all_cond & cond
            # @when_all((all_cond))
            # def action_handler(c):
            #     self.logger.error("caught an unregistered event: '{}'".format(c.m))
            
                

                    
    # def build_condition(self, dict_rule: dict):
    #     # {"m": {"type": "greeting"}}
    #     if "m" in dict_rule:
    #         # print("building condition: {}".format(dict_rule))
    #         expr = None
    #         for key, value in dict_rule["m"].items():
    #             part = getattr(m, key) == value
    #             # print(part.value)
    #             expr = part if expr is None else expr & part
    #             # print(expr)
    #         return expr


    # def build_timer_condition(self, all_clause: list):
    #     condition = []
    #     for i, clause in enumerate(all_clause):
    #         self.logger.info("building sub-condition {} for multi-event clause: {}".format(i, all_clause))
    #         if not isinstance(clause, dict) or "m" not in clause:
    #             raise ValueError(f"Invalid clause (missing 'm' or no dict): {clause}")
    #         if i >= len(self._BIND_NAMES):
    #             raise ValueError("Too many partial clauses; extend _BIND_NAMES")
    #         cond =  self.build_s_expr(clause["m"])
    #         condition.append(getattr(s, f"seen_{self._BIND_NAMES[i]}") << self.build_m_expr(clause["m"]))
    #     return condition

    def build_condition(self, all_clause: dict|list): 
        """
        Supports:
        - {"m": {...}}  (single-event)
        - [{"m":{...}}, {"m":{...}}] (multi-event / partial match)
        Returns: (condition)
        """
        # Case 1: Single-event style: {"m": {...}}
        if isinstance(all_clause, dict) and "m" in all_clause:
            self.logger.info("building single-event condition: {}".format(all_clause))
            return self.build_m_expr(all_clause["m"])

        # Case 2: multi-event style (partial match): [{"m": {...}}, {"m": {...}}, ...]
        if isinstance(all_clause, list):
            events = []
            condition = []

            for i, clause in enumerate(all_clause):
                self.logger.info("building sub-condition {} for multi-event clause: {}".format(i, all_clause))
                if not isinstance(clause, dict) or "m" not in clause:
                    raise ValueError(f"Invalid clause (missing 'm' or no dict): {clause}")
                if i >= len(self._BIND_NAMES):
                    raise ValueError("Too many partial clauses; extend _BIND_NAMES")
                condition.append(getattr(c, self._BIND_NAMES[i]) << self.build_m_expr(clause["m"]))
                # print(clause)
                # condition.append(self.build_m_expr(clause["m"]))
                # print(condition[-1].__dict__)
            return  condition #, events
        
        raise ValueError(f"Unsupported 'all' clause format: {all_clause}")


    def build_m_expr(self, m_dict: dict) -> value:
        """Builds an AND expression for fields inside a single message."""
        # {"type": "greeting", "phrase": "hello"}
        expr = None
        for key, value in m_dict.items():
            part = getattr(m, key) == value
            expr = part if expr is None else (expr & part)
        return expr
    
    def devices_and_calls_exist(self, bind: dict) -> bool:
        for dev in bind["with"]:
            if dev not in self.datastore.devices_objects and dev not in self.datastore.pins_objects:
                self.logger.warning("Device '{}' not found in datastore for binding: {}".format(dev, bind))
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
    b.datastore.add_device("pt1", pt1, {"on": pt1.on, "off": pt1.off})
    b.datastore.add_device("pt2", pt2, {"on": pt2.on, "off": pt2.off}) 

    binding_to_pin =  { "with": ["pt1"], #"""The unique_id of the entity this binding belongs to."""
                        "ruleset_name": "pt1_to_pt2",
                        "rulesets":  {
                            "p_on": {
                                "when": {"all": { "m": { "value": "on" } } },
                                "run": {"id": "pt2", "call": "on"}
                            } ,
                            "p_off": {
                                "when": { "all":  { "m": {"value": "off" } }},
                                "run": {"id": "pt2", "call": "off"}
                            }}
                        
                    }
   
    b.new_binding(binding_to_pin)
    post_event("pt1_to_pt2", "on", b.datastore, b.logger)


