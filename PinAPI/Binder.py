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
from durable.engine import MessageNotHandledException, MessageObservedException
# import yaml
import json
from typing import Any, Dict, Callable
from PinAPI.DataStore import DataStore
import time
import threading
from collections.abc import Mapping, Sequence

_event_names = ["first", "second", "third", "fourth", "fifth", "sixth"]

def print_timer(c):
    print("timer action")


class pintest():
    def __init__(self, id: str):
        self.id = id

    def on(self, t="-" ):
        print("{} is on with t={}".format(self.id, t))
        # t.x 
        return True

    def off(self, t="-" ):
        print("{} is off with t={}".format(self.id, t))
        return True

def iter_parents(tree, child_key, path=()):
    """
    Yield tuples (path, run_value) where path shows how to reach the dict containing 'run'.
    Path elements are dict keys or list indices.
    """
    # print(isinstance(tree, Mapping))
    if isinstance(tree, Mapping):
        if child_key in tree:
            yield (path + (child_key,), tree)

        for k, v in tree.items():
            yield from iter_parents(v, child_key, path + (k,))
    
    elif isinstance(tree, Sequence) and not isinstance(tree, (str, bytes, bytearray)):
        for i, item in enumerate(tree):
            yield from iter_parents(item, child_key, path + (i,))


def post_event(unique_id, payload: dict, datastore: DataStore, logger: logging.Logger):
        for ruleset in datastore.get_bindings(unique_id):
            logger.info("posting event to ruleset {}: {}".format(ruleset["name"], payload))   
            # rule_state = get_host().get_ruleset(ruleset["name"]).get_definition()
            # print 
            # payload["any"] = True
            try: 
                # if ruleset["time_out"]:
                #     post(ruleset["name"], {"time_out": ruleset["time_out"], "ruleset": ruleset["name"], "fact": payload})
                #     assert_fact(ruleset["name"], payload) 
                # else:          
                #     post(ruleset["name"], payload) 
                post(ruleset["name"], payload) 
            
            except MessageNotHandledException as e:
                    # print(type(e))
                    logger.error("Unmatched event: {}".format(e.message))
            except MessageObservedException as e:
                    logger.error("Event has already been observed: {}".format(e.message))
            # retract_fact(ruleset["name"], payload)

# def start_timer(time, callback):
#     timer = threading.Timer(time, callback)
#     timer.daemon = True    
#     timer.start()
            
def build_error_handler(_rule_set_name: str, _logger: logging.Logger):
    def error_handler(c):
        _logger.error("caught an exception: {}".format(c.s.exception))
        c.s.exception = None
    error_handler.__name__ = f"error_handler__{_rule_set_name}"
    return error_handler

def build_condition_handler(_path :list, _run_parent:dict|list, _logger: logging.Logger, _datastore:DataStore):
    _rule_name = _path[0]
    _run_path = _path[1]
    if isinstance(_run_parent, list):
        pass
    else:
        action = build_action(_run_path, _run_parent, _logger, _datastore)
    def condition_handler(c):
        c.s.return_value = {"value": "pending"}
        for event_name in _event_names:
            event = getattr(c, event_name)
            if not event is  None:
                

                _logger.info("rule fired by {} with data {}".format(event_name, event ))
                if hasattr(event, 'post_time'):
                    _logger.info(getattr(c, 'post_time'))
        action(c)
    condition_handler.__name__ = f"handler__{_rule_name}"
    return condition_handler

def build_action(rule_name: str, run_def: dict, logger: logging.Logger, datastore:DataStore):
    # capture everything in the closure
    device_id = run_def.get("id")
    call_name = run_def.get("call")

    def action(c, _rule_name=rule_name, _device_id=device_id, _call_name=call_name):
        logger.info("rule fired: %s", _rule_name)
        action_function = datastore.get_functions(_device_id).get(_call_name)
        if action_function is None:
            logger.warning("no action function '%s' for device '%s'", _call_name, _device_id)
            return
        result = action_function()  
        c.s.return_value = { "value": True if result is None else bool(result) }
    # give it a stable name for debugging
    action.__name__ = f"action__{rule_name}"
    return action



class Binder:
    def __init__(self, datastore: DataStore):
        self.logger = logging.getLogger("Binder")
        self.datastore = datastore

    def devices_and_calls_exist(self, bind: dict) -> bool:
        for ruleset in bind.keys():
            for rule_name in bind[ruleset].keys():
                # print("checking:", ruleset, rule_name, bind[ruleset][rule_name])
                rule_def = bind[ruleset][rule_name]
                if "run" not in rule_def:
                    self.logger.warning("Missing 'run' definition in rule '{}' of ruleset '{}'".format(rule_name, rule_def))
                    return False                
                if "all" not in rule_def and "any" not in rule_def:
                    self.logger.warning("Missing 'all|any' definition in rule '{}' of ruleset '{}'".format(rule_name, rule_def))
                    return False
                
                run_def = rule_def["run"]
                if isinstance(run_def, list):
                    for run in run_def:
                        if not self.check_call(run, rule_name):
                            return False
                else:
                    if not self.check_call(run_def,rule_name):
                        return False
                
                if "time_out" in bind:
                    if (not isinstance(bind["time_out"], int) or bind["time_out"] < 0):
                        self.logger.warning("Invalid 'time_out' value in binding: {}".format(bind["time_out"]))
                        return False
        return True

    def check_call(self, run_def:dict|list, rule_name:str) -> bool:
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

    def new_binding(self, bind: dict):
        # if not self.devices_and_calls_exist(bind):
        #     return


        # store bindings such that devices (listed by "id" in "all") can find the rulesets to post messages to 
        for path, all_parent in iter_parents(bind, "all"):
            for id_path, id_parent in iter_parents(all_parent['all'], 'id'): 
                # print("id", path, id_parent['id'])
                if id_parent['id'] not in self.datastore.devices_objects and id_parent['id'] not in self.datastore.pins_objects:
                    self.logger.warning("Device '{}' not found in datastore for binding: {}".format(id_parent['id'], bind))
                    return
                self.datastore.add_binding(id_parent['id'], path[0])

        # build the condition handler with the action(s) defined in "run"
        for path, run_parent in iter_parents(bind, "run"):
            # print("run", path, run_parent['run'])
            if isinstance(run_parent['run'], dict):
                run_parent['run'] = build_condition_handler(path, run_parent['run'], self.logger, self.datastore)
            elif isinstance(run_parent['run'], list):
                for i, run_def in enumerate(run_parent['run']):
                    if isinstance(run_def, dict):
                        run_parent['run'] = build_condition_handler(path, run_def, self.logger, self.datastore)
                    # else:
                    #     run_parent['run'] = print_timer
            else:
                run_parent['run'] = print_timer

        # add an error hendler event to catch e.g. action errors. 
        # for ruleset in bind.keys():
        #     bind[ruleset]['error_handle'] = {
        #     "all": [{"m": {"$and": [
        #                             { "$ex": {"exception": 1}},
        #                             { "$s": 1 }  
        #                             ]}}],
        #     "run":   build_error_handler(ruleset, self.logger )
        # }

        print(bind)
        get_host().set_rulesets(bind)
        
        # for path, run_parent in iter_parents(bind, "all"):
        #     if isinstance(run_parent['all'], list):
        #         for rule in run_parent['all']:
        #             pass
        return

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

    # def set_rule(self, ruleset_name: str, rules: dict, time_out: int = 0):
    #     conditions = []
    #     # build actions
    #     actions = {}
    #     for rule_name, rule_def in rules.items(): 
    #         actions[rule_name] = build_action_for_rule(rule_name, rule_def, self.logger, self.datastore)

    #     with ruleset(ruleset_name): 
    #         for rule_name, rule_def in rules.items(): 
    #             self.logger.info("building rule: {}".format(rule_name))
    #             condition = self.build_condition(rule_def.get("when").get("all"))
    #             action = actions[rule_name]
    #             # action = build_action(rules, self.logger, self.datastore)

    #             if isinstance(condition, list):
    #                 for cond in condition: 
    #                     conditions.append(cond) 
    #             else: 
    #                 conditions.append(condition) 

    #             if isinstance(condition, list):
    #                 event_handler = build_event_handler(_rule_name=rule_name, _action=action, _logger=self.logger)
    #                 when_all(*condition)(event_handler)
                    
    #                 if time_out > 0:
    #                     @when_all(+m.time_out)
    #                     def set_timer(c):
    #                         self.logger.info("starting timeout timer for rule '{}' with time_out {} seconds".format(rule_name, time_out))
    #                         c.start_timer("timer", int(c.m.time_out)) 
    #             else:

    #                 handler = build_condition_handler(_rule_name=rule_name, _action=action, _logger=self.logger)
    #                 when_all(condition)(handler)
                   
    #         # Catch exceptions in rules and its actions
    #         @when_all(+s.exception)
    #         def action_handler(c):
    #             self.logger.error("caught an exception: {}".format(c.s.exception))
    #             c.s.exception = None
            
    #         if isinstance(condition, list) and time_out > 0:
    #             @when_all(timeout("timer"))
    #             def handle_time_out(c):
    #                 self.logger.info("not all events arived withing the time_out time, retracting partial matches")
    #                 for cond in conditions:
    #                     retract_fact(ruleset_name=ruleset_name, fact={"value": cond._right, "any": True}) 
                       

    # def build_condition(self, all_clause: dict|list): 
    #     """
    #     Supports:
    #     - {"m": {...}}  (single-event)
    #     - [{"m":{...}}, {"m":{...}}] (multi-event / partial match)
    #     Returns: (condition)
    #     """
    #     # Case 1: Single-event style: {"m": {...}}
    #     if isinstance(all_clause, dict) and "m" in all_clause:
    #         self.logger.info("building single-event condition: {}".format(all_clause))
    #         return self.build_m_expr(all_clause["m"])

    #     # Case 2: multi-event style (partial match): [{"m": {...}}, {"m": {...}}, ...]
    #     if isinstance(all_clause, list):
    #         events = []
    #         condition = []

    #         for i, clause in enumerate(all_clause):
    #             self.logger.info("building sub-condition {} for multi-event clause: {}".format(i, all_clause))
    #             if not isinstance(clause, dict) or "m" not in clause:
    #                 raise ValueError(f"Invalid clause (missing 'm' or no dict): {clause}")
    #             if i >= len(self._BIND_NAMES):
    #                 raise ValueError("Too many partial clauses; extend _BIND_NAMES")
    #             condition.append(getattr(c, self._BIND_NAMES[i]) << self.build_m_expr(clause["m"]))
    #             # print(clause)
    #             # condition.append(self.build_m_expr(clause["m"]))
    #             # print(condition[-1].__dict__)
    #         return  condition #, events
        
    #     raise ValueError(f"Unsupported 'all' clause format: {all_clause}")


    # def build_m_expr(self, m_dict: dict) -> value:
    #     """Builds an AND expression for fields inside a single message."""
    #     # {"type": "greeting", "phrase": "hello"}
    #     expr = None
    #     for key, value in m_dict.items():
    #         part = getattr(m, key) == value
    #         expr = part if expr is None else (expr & part)
    #     return expr
    
    
    

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


