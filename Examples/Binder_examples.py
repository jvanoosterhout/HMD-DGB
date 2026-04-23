"""
Stand-alone Binder test example

This script provides a stand-alone test environment for the HMD-DGB Binder. Its goal is to offer example bindings and make it easy to experiment with custom bindings before running them in an integrated setup (e.g. with Home Assistant, MQTT, or physical GPIO).
The script initializes the Binder with an in-memory DataStore and defines several dummy devices. These devices simulate both event sources and actors, allowing Binder behavior to be tested without external dependencies. Some dummy devices expose callable actions (on, off) to act as controllable outputs.
Four binding patterns are demonstrated:

Direct durable binding
A simple rule binds a source (s1) directly to an actor (p1).
on and off events from the source immediately trigger the corresponding action on the actor.

Paired event binding
This rule requires two separate events—one command (s2) and one password (pw1)—to occur before the action is executed.
Events may arrive in any order, enabling basic authorization or confirmation logic.

Delayed action with timer
A delayed auto-off pattern is implemented using a background timer.
An on event triggers the action immediately and starts a timer; when the timer expires, a timeout event switches the actor off.

Statechart with timeout
A statechart enforces a two-step command (command + password) within a time window.
If both events arrive in time, the action is executed; otherwise, the state resets and a timeout is logged. This pattern is useful for preventing accidental or unsafe actions.

After starting the Binder's event dispatcher, all rule sets are loaded and a sequence of test events is posted. The script then waits briefly and shuts down cleanly.
This setup offers a compact sandbox for validating Binder logic and experimenting with rules and statecharts before deploying them in a fully integrated environment.
"""

import time
import DGB.Binder
import DGB.DataStore
import logging


# setup the binder class with durable rules
binder = DGB.Binder.Binder(DGB.DataStore.DataStore())
logging.basicConfig(level=logging.INFO)
binder.logger.setLevel("INFO")
binder.logger.info("starting test_binder")


# define a dummy device to act as scource (event/trigger) and actor
class dummy_device:
    def __init__(self, id: str):
        self.id = id

    def on(self, t="-"):
        print("{} is on".format(self.id))
        return True

    def off(self, t="-"):
        print("{} is off".format(self.id))
        return True


# make instances of the dummy device
p1 = dummy_device("pin1")
s1 = dummy_device("source1")
s2 = dummy_device("source2")
s3 = dummy_device("source3")
s4 = dummy_device("source4")
pw1 = dummy_device("pw1")
pw2 = dummy_device("pw2")

# add instances with theire calable functions (if any) to the datastore
binder.datastore.add_device("p1", p1, {"on": p1.on, "off": p1.off})
binder.datastore.add_device("s1", s1)
binder.datastore.add_device("s2", s2)
binder.datastore.add_device("s3", s3)
binder.datastore.add_device("s4", s4)
binder.datastore.add_device("pw1", pw1)
binder.datastore.add_device("pw2", pw2)

# define durable rules in json format
# this is a standart rule, all conditions must match at the same time
binding_to_pin = {
    "s1_to_p2": {
        "p_on": {
            "all": [{"m": {"$and": [{"unique_id": "s1"}, {"payload": "on"}]}}],
            "run": {"action": {"unique_id": "p1", "call": "on"}},
        },
        "p_off": {
            "all": [{"m": {"$and": [{"unique_id": "s1"}, {"payload": "off"}]}}],
            "run": {"action": {"unique_id": "p1", "call": "off"}},
        },
    }
}

# this is an event rule, the first and second condition may arrive separatly
binding_to_pin_with_pw = {
    "s2_to_p1": {
        "p_on": {
            "all": [
                {"first": {"unique_id": "s2", "payload": "on"}},
                {"second": {"unique_id": "pw1", "payload": "secret"}},
            ],
            "run": {"action": {"unique_id": "p1", "call": "on"}},
        },
        "p_off": {
            "all": [
                {"third": {"unique_id": "s2", "payload": "off"}},
                {"second": {"unique_id": "pw1", "payload": "secret"}},
            ],
            "run": {"action": {"unique_id": "p1", "call": "off"}},
        },
    }
}

# This is a rule with a durable-like timer. Timers do not seem to work when
# imported from json. This implemenation uses threading to run timers in the
# background. The timeout allows to trigger a delayed event.
binding_auto_off = {
    "delayed_action": {
        "p_on": {
            "all": [{"m": {"$and": [{"unique_id": "s4"}, {"payload": "on"}]}}],
            "run": [
                {"timer": {"name": "auto_off", "action": "start", "seconds": 3}},
                {"action": {"unique_id": "p1", "call": "on"}},
            ],
        },
        "timeout": {
            "all": [{"m": {"timeout": "auto_off"}}],
            "run": {"action": {"unique_id": "p1", "call": "off"}},
        },
    }
}

# this is a statechart, not a rule. The state chart with timers allow
# to wait for multiple commands to match. In my use-case: have a
# double action command to preven acidental control of devices. More
# specific: I want my garage only to be opend via the Home Assistant
# cover entity when I provide the right pasword
binding_to_pin_with_pw_with_timeout = {
    "s3_to_p1_timed$state": {
        "start": {"t_0": {"to": "waiting"}},
        "waiting": {
            "t_s3_on": {
                "all": [{"m": {"$and": [{"unique_id": "s3"}, {"payload": "on"}]}}],
                "to": "got_s3_on",
                "run": {
                    "timer": {"name": "PairTimeout", "action": "start", "seconds": 1}
                },
            },
            "t_pw_secret": {
                "all": [{"m": {"$and": [{"unique_id": "pw2"}, {"payload": "secret"}]}}],
                "to": "got_secret",
                "run": {
                    "timer": {"name": "PairTimeout", "action": "start", "seconds": 1}
                },
            },
        },
        "got_s3_on": {
            "t_pw_secret": {
                "all": [{"m": {"$and": [{"unique_id": "pw2"}, {"payload": "secret"}]}}],
                "to": "waiting",
                "run": [
                    {"timer": {"name": "PairTimeout", "action": "cancel"}},
                    {"action": {"unique_id": "p1", "call": "on"}},
                ],
            },
            "t_timeout": {
                "all": [{"m": {"timeout": "PairTimeout"}}],
                "to": "waiting",
                "run": {"log": {"msg": "timeout while waiting for password"}},
            },
        },
        "got_secret": {
            "t_s3_on": {
                "all": [{"m": {"$and": [{"unique_id": "s3"}, {"payload": "on"}]}}],
                "to": "waiting",
                "run": [
                    {"timer": {"name": "PairTimeout", "action": "cancel"}},
                    {"action": {"unique_id": "p1", "call": "on"}},
                ],
            },
            "t_timeout": {
                "all": [{"m": {"timeout": "PairTimeout"}}],
                "to": "waiting",
                "run": {"log": {"msg": "timeout while waiting for on command"}},
            },
        },
    }
}


# start the binder
binder.start_event_dispatcher()

# load the rulesets
binder.datastore.put_to_queue("ruleset", binding_to_pin)
binder.datastore.put_to_queue("ruleset", binding_to_pin_with_pw)
binder.datastore.put_to_queue("ruleset", binding_auto_off)
binder.datastore.put_to_queue("ruleset", binding_to_pin_with_pw_with_timeout)

# post the events
binder.datastore.put_to_queue("post", {"unique_id": "s1", "payload": "on"})
binder.datastore.put_to_queue("post", {"unique_id": "s2", "payload": "on"})
binder.datastore.put_to_queue("post", {"unique_id": "pw1", "payload": "secret"})
binder.datastore.put_to_queue("post", {"unique_id": "s3", "payload": "on"})
binder.datastore.put_to_queue("post", {"unique_id": "pw2", "payload": "secret"})
binder.datastore.put_to_queue("post", {"unique_id": "s4", "payload": "on"})

time.sleep(10)
# shutdown the main binder thread
binder.datastore.put_to_queue("shutdown", {})
