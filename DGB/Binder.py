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
from DGB.DataStore import DataStore
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


def build_condition_handler(_path :list, _run_parent:dict|list, _logger: logging.Logger, _datastore:DataStore):
    _rule_name = _path[0]
    _run_path = _path[1]
    if isinstance(_run_parent, list):
        action = []
        for a in _run_parent:
            if 'timer' in a:
                action.append(build_timer(_rule_name, _run_path, a, _logger, _datastore))
                # action = build_timer(_run_path, a, _logger)
            else :
                action.append(build_action(_run_path, a, _logger, _datastore))
                # action = build_action(_run_path, a, _logger, _datastore)
    else:
        if 'timer' in _run_parent:
            action = build_timer(_rule_name, _run_path, _run_parent, _logger, _datastore)
        else :
            action = build_action(_run_path, _run_parent, _logger, _datastore)
    def condition_handler(c):
        c.s.return_value = {"value": "pending"}
        for event_name in _event_names:
            event = getattr(c, event_name)
            if not event is  None:
                _logger.info("rule fired by {} with data {}".format(event_name, event ))
                if hasattr(event, 'post_time'):
                    _logger.info(getattr(c, 'post_time'))
        if isinstance(action, list):
            for a in action:
                # _logger.info("action in list")
                a(c)
        else:
            action(c)
            # _logger.info("action alone")
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

timers: dict[str, threading.Timer] = {}
timers_lock = threading.Lock()

def start_timer(timer_id: str, delay_seconds: float, timer_callback: callable):
    """
    Start a timer and register it by ID.
    """
    if timer_id in timers:
        cancel_timer(timer_id)
    timer = threading.Timer(delay_seconds, timer_callback)
    with timers_lock:
        timers[timer_id] = timer
    timer.start()

def cancel_timer(timer_id: str) -> bool:
    """
    Cancel a running timer.
    Returns True if cancelled, False if not found.
    """
    with timers_lock:
        if timer_id in timers:
            timers[timer_id].cancel()
        timers.pop(timer_id, None)
        return True
    return False

def build_timer(rule_set:str, rule_name: str, run_def: dict, logger: logging.Logger, datastore:DataStore):
    cfg = run_def.get('timer')
    if not cfg:
        return
    name = cfg.get('name')
    action = cfg.get('action')
    seconds = cfg.get('seconds')
    if not name or not action:
        raise ValueError('Timer action requires name and action')

    def timer(c, _rule_name=rule_name, name=name, action=action, seconds=seconds):
        if action == 'start':
            logger.info("Timer %s started for: %s", name, _rule_name)
            if seconds is None:
                raise ValueError('Timer start requires seconds')
            def callback():
                rule_set_name = rule_set.split('$', 1)[0]
                datastore.put_to_queue('post', {"rulesetname": rule_set_name, "payload": {"timeout" : name, "dummy": "dummy"}})
            start_timer(name, seconds, callback)
  
        elif action == 'cancel':
            logger.info("Timer %s canceled for: %s", name, _rule_name)
            cancel_timer(name)

        else:
            raise ValueError(f'Unknown timer action: {action}')

    timer.__name__ = f"timer__{rule_name}__{name}"
    return timer


class Binder:
    def __init__(self, datastore: DataStore):
        self.logger = logging.getLogger("Binder")
        self.datastore = datastore
        
    def start_event_dispatcher(self): 
        while True:
            cmd, payload = self.datastore.post_queue.get()
            # if cmd == 'shutdown':
            #     self.logger.info("Dispatcher shutdown requested")
            #     break

            if cmd == 'post':
                if not 'unique_id' in payload and not 'rulesetname' in payload:
                    self.logger.error("no unique_id or rulesetname in payload")
                    return
                if not 'payload' in payload:
                    self.logger.error("no payload in payload")
                    return
                ruleset = []
                if 'unique_id' in payload: 
                    ruleset = self.datastore.get_bindings(payload['unique_id'])
                else:
                    ruleset = [{'name': payload['rulesetname']}]
                try: 
                    with self.datastore.engine_lock:
                        for set in ruleset:
                            self.logger.info("Posting event to ruleset {}: {}".format(set['name'], payload['payload']))
                            post(set['name'], payload['payload']) 
                    
                except MessageNotHandledException as e:
                        self.logger.error("Unmatched event: {}".format(e.message))
                except MessageObservedException as e:
                        self.logger.error("Event has already been observed: {}".format(e.message))
                except:
                        self.logger.error(f"Unknown exeption for {set}")
                finally:
                    self.datastore.post_queue.task_done()
                    
            elif cmd == 'ruleset':
                self.logger.warning('not implemented jet')

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
            if isinstance(run_parent['run'], dict) or isinstance(run_parent['run'], list):
                run_parent['run'] = build_condition_handler(path, run_parent['run'], self.logger, self.datastore)
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
        with self.datastore.engine_lock:
            get_host().set_rulesets(bind)
        
        return

