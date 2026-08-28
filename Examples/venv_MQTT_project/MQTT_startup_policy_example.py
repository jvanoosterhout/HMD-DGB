"""Run the test configuration with startup policy preloaded.

The retained startup policy is published before DGBservice starts. Three seconds
after startup, the switch and sensor configuration sets are published.
"""

import json
import threading

import paho.mqtt.publish as mqtt_publish

from DGB.DGBservice import DGBservice

NAME = "42-controller"
BROKER = "192.168.70.100"
PORT = 1882
USERNAME = "mqtt_broker"
PASSWORD = "mqtt_broker"

STARTUP_POLICY = {
    "startup_policy": {
        "loading_mode": "gated",
        "error_state_policy": "clear_affected_config_and_restart",
    }
}

SWITCH_CONFIG = {
    "Devices": [
        {
            "EntityInfo": {
                "name": "switch test",
                "component": "switch",
                "unique_id": "rpi4-switch-test",
                "device": {
                    "name": "HMD-DGB-test-device",
                    "model": "Raspberry Pi 4",
                    "manufacturer": "Jeroen van Oosterhout",
                    "sw_version": "none",
                    "hw_version": "RPi4",
                    "identifiers": "rpi4_test",
                },
            }
        }
    ],
    "Pins": [
        {
            "PinInfo": {
                "pin": 20,
                "ptype": "out",
                "initial": 0,
                "active_state": True,
                "value": 0,
                "blink": 1,
            }
        }
    ],
    "state_initialization": {
        "preset_value": [
            {
                "unique_id": "rpi4-switch-test",
                "call": "set_state",
                "args": [{"state_name": "state", "state": "ON"}],
            },
            {
                "unique_id": "20",
                "call": "set_state",
                "args": [{"state_name": "state", "state": "on"}],
            },
        ]
    },
    "Bindings": [
        {
            "BindInfo": {
                "switch_test_to_pin_20": {
                    "p_on": {
                        "all": [
                            {
                                "m": {
                                    "$and": [
                                        {"unique_id": "rpi4-switch-test"},
                                        {"payload": "ON"},
                                    ]
                                }
                            }
                        ],
                        "run": {"action": {"unique_id": "20", "call": "on"}},
                    },
                    "p_off": {
                        "all": [
                            {
                                "m": {
                                    "$and": [
                                        {"unique_id": "rpi4-switch-test"},
                                        {"payload": "OFF"},
                                    ]
                                }
                            }
                        ],
                        "run": {"action": {"unique_id": "20", "call": "off"}},
                    },
                }
            }
        }
    ],
}

SENSOR_CONFIG = {
    "Devices": [
        {
            "EntityInfo": {
                "name": "sensor test",
                "component": "sensor",
                "unique_id": "rpi4-sensor-test",
                "device": {
                    "name": "HMD-DGB-test-device",
                    "model": "Raspberry Pi 4",
                    "manufacturer": "Jeroen van Oosterhout",
                    "sw_version": "none",
                    "hw_version": "RPi4",
                    "identifiers": "rpi4_test",
                },
            }
        }
    ],
    "Pins": [
        {
            "PinInfo": {
                "pin": 21,
                "ptype": "count",
                "when_activated": True,
                "when_deactivated": True,
            }
        }
    ],
    "state_initialization": {
        "retain_state": [
            {"unique_id": "rpi4-sensor-test", "call": ["set_state"]},
            {"unique_id": "21", "call": ["set_state"]},
        ],
        "preset_value": [
            {
                "unique_id": "21",
                "call": "set_state",
                "args": [{"state_name": "count_total", "state": 42}],
            }
        ],
    },
    "Bindings": [
        {
            "BindInfo": {
                "pin_21_to_sensor_test": {
                    "p_on": {
                        "all": [
                            {
                                "m": {
                                    "$and": [
                                        {"unique_id": "21"},
                                        {"$ex": {"payload": 1}},
                                    ]
                                }
                            }
                        ],
                        "run": {
                            "action": {
                                "unique_id": "rpi4-sensor-test",
                                "call": "set_state",
                                "args": [
                                    {
                                        "state_name": "state",
                                        "state": "$m.payload",
                                    }
                                ],
                            }
                        },
                    }
                }
            }
        }
    ],
}


def publish(topic: str, payload: dict, retain: bool = False) -> None:
    mqtt_publish.single(
        topic,
        payload=json.dumps(payload),
        hostname=BROKER,
        port=PORT,
        auth={"username": USERNAME, "password": PASSWORD},
        qos=1,
        retain=retain,
    )


def publish_device_configs() -> None:
    topic_base = f"config/{NAME}/devices/test"
    publish(f"{topic_base}/set1", SWITCH_CONFIG)
    publish(f"{topic_base}/set2", SENSOR_CONFIG)


def main() -> None:
    publish(f"config/{NAME}/startup-policy", STARTUP_POLICY, retain=True)

    dgb = DGBservice(
        name=NAME,
        broker=BROKER,
        username=USERNAME,
        password=PASSWORD,
        location="area-42",
        port=PORT,
        system_sensor_update_rate=300,
    )
    threading.Timer(3, publish_device_configs).start()
    dgb.run_forever()


if __name__ == "__main__":
    main()
