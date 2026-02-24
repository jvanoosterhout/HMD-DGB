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
from durable.lang import ruleset, when_all, when_start, when_any, m, c, s, any, all, none, post, get_host, get_state, timeout, update_state, assert_fact, retract_fact, value  # Durable Python DSL
from durable.engine import MessageNotHandledException
# import yaml
import json
from typing import Any, Dict, Callable
from PinAPI.DataStore import DataStore
import time
import threading

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
            
            payload["any"] = True
            try: 
                if ruleset["time_out"]:
                    post(ruleset["name"], {"time_out": ruleset["time_out"], "ruleset": ruleset["name"], "fact": payload})
                    assert_fact(ruleset["name"], payload) 
                    # TODO: post event that sets timer to retract fact in payload after ruleset["timeout"]
                else:          
                    post(ruleset["name"], payload) 
            
            except MessageNotHandledException as e:
                    # print(type(e))
                    logger.error("Unmatched event (You can ignore key and value 'any': True): {}".format(e.message))

def start_timer(time, callback):
    timer = threading.Timer(time, callback)
    timer.daemon = True    
    timer.start()
            
        # time.sleep(0.1)  # wait a bit for rules to process the event and set return_value in state
        # time_out = 2
        # succes_array = []
        # for ruleset in datastore.get_bindings(unique_id):
        #     returend = False
        #     now = time.time()
        #     while not returend and (time.time() - now < time_out):
        #         rule_state = get_state(ruleset["name"])
        #         logger.info("state of ruleset {}: {}".format(ruleset["name"], rule_state))
        #         if 'return_value' in rule_state:
        #             state = rule_state["return_value"]["value"] 
        #             if state == "pending":
        #                  logger.info("rule {} is still pending, waiting...".format(ruleset["name"]))
        #                  time.sleep(0.5)
        #                  pass
        #             returend = True
        #             succes_array.append(state )
        #             del rule_state["return_value"]
        #             update_state(ruleset["name"], rule_state)  # clear return_value after reading
        #         time.sleep(0.5)  # wait a bit before checking again

        # logger.info("final state after posting to rulesets {}: {}".format(datastore.get_bindings(unique_id), succes_array))

def build_action(rules: dict, logger: logging.Logger, datastore: DataStore):
    def action(c): 
        # Look up the Python function by name 
        for rule_name, rule_def in rules.items():
            # identify the fired rule to find the right action to execute (in case of multiple rules in one ruleset)
            if isinstance(rule_def.get("when").get("all"), list):
                rule_identifier = rule_def.get("when").get("all")[0].get("m")  # assuming the first condition has a discriminative "value" field
                input_identifier = c.first  # the value from the first event
            else:
                rule_identifier = rule_def.get("when").get("all").get("m")  # assuming a single condition with "m"
                input_identifier = c.m  # the value from the event
            logger.info("checking rule '{}' with condition value '{}' against event value '{}'".format(rule_name, rule_identifier, input_identifier))
            
            if rule_identifier.get("value") == input_identifier["value"]: 
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
            ruleset_name = bind["ruleset_name"] if "ruleset_name" in bind else "ruleset_{}".format(len(self.datastore.bindings))

            if self.devices_and_calls_exist(bind):
                self.logger.info("creating binding '{}' with ruleset: {}".format(ruleset_name, bind["rulesets"]))
                time_out = bind["time_out"] if "time_out" in bind else 0
                self.set_rule(ruleset_name, bind["rulesets"], time_out)
                for dev in bind["with"]:
                    self.datastore.add_binding(dev, ruleset_name, time_out)
            else:
                self.logger.warning("Invalid binding configuration, device(s) or call(s) not found for: {}".format(bind))
        else:
            self.logger.warning("Invalid binding configuration, missing 'with' or 'rulesets' key: {}".format(bind))

    def set_rule(self, ruleset_name: str, rules: dict, time_out: int = 0):
        conditions = []
        with ruleset(ruleset_name): 
            for rule_name, rule_def in rules.items(): 
                self.logger.info("building rule: {}".format(rule_name))
                condition = self.build_condition(rule_def.get("when").get("all"))
                action = build_action(rules, self.logger, self.datastore)

                if isinstance(condition, list):
                    for cond in condition: 
                        conditions.append(cond) 
                else: 
                    conditions.append(condition) 

                if isinstance(condition, list):
                    @when_all(*condition)
                    def action_handler(c):
                        self.logger.info("all conditions met, executing action")
                        c.s.return_value = {"value": "pending"}
                        action(c)
                        if time_out > 0:
                            c.cancel_timer('timer')
                            for cond in conditions:
                                retract_fact(ruleset_name=ruleset_name, fact={"value": cond._right, "any": True}) 
                    
                    if time_out > 0:
                        @when_all(+m.time_out)
                        def set_timer(c):
                            self.logger.info("starting timeout timer for rule '{}' with time_out {} seconds".format(rule_name, time_out))
                            # print(type(c.m.time_out))
                            # c.start_timer('MyTimer', 5)
                            c.start_timer("timer", int(c.m.time_out)) 

                else:
                    @when_all(condition)
                    def action_handler(c):
                        c.s.return_value = {"value": "pending"}
                        action(c)
            
            # Catch exceptions in rules and its actions
            @when_all(+s.exception)
            def action_handler(c):
                self.logger.error("caught an exception: {}".format(c.s.exception))
                c.s.exception = None
            
            if isinstance(condition, list) and time_out > 0:
                @when_all(timeout("timer"))
                def handle_time_out(c):
                    self.logger.info("not all events arived withing the time_out time, retracting partial matches")
                    for cond in conditions:
                        retract_fact(ruleset_name=ruleset_name, fact={"value": cond._right, "any": True}) 
            # Catch-all rule
            # @when_all(+m.any)
            # def fallback(c):
            #     print(c.m)
            #     self.logger.warning("Caught a multi-event or unmatched event: {}".format({"value": c.m.value}))
            #     c.s.matched = False  # reset for next event
            
            

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
            
            if "time_out" in bind:
                if (not isinstance(bind["time_out"], int) or bind["time_out"] < 0):
                    self.logger.warning("Invalid 'time_out' value in binding: {}".format(bind["time_out"]))
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


