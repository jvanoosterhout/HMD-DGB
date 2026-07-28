"""
This example is meant to testrun the package over a longer periode of time with end-to-end configuration between Home Assistant entities and physical GPIO pins using durable bindings. It includes a binding with a timer loop. Each loop it turns a gpio out on or off. The gpio coneccts to another gpio in which it turn (de)activates a sensor.

timer → GPIO output → GPIO input → Sensor
"""

import json
import threading

import pkg_resources

from DGB.DGBservice import DGBservice


def main():
    dgb = DGBservice(
        name="rpi28",
        broker="192.168.70.100",
        username="mqtt_broker",
        password="mqtt_broker",
        port=1882,
    )
    # dgb = Pin_mqtt(name = "rpi", broker="ip-adres",username="mqtt_user", password="mqtt_pw", port=1882)
    # atexit.register(dgb.__del__)
    DeviceInfo = {
        "name": "HMD-DGB-duration-test-device",
        "model": "Raspberry Pi zero 2w",
        "manufacturer": "Raspberry Pi Holdings",
        "sw_version": pkg_resources.get_distribution(
            "ha-mqtt-discoverable-device-gpio-binder"
        ).version,  # """Firmware version of the device"""
        "hw_version": "RPizero",  # """Hardware version of the device"""
        "identifiers": "rpi0_duration_test",  # """A list of IDs that uniquely identify the device. For example a serial number."""
    }

    EntityInfo = {
        "device": DeviceInfo,  # """Information about the device this sensor belongs to"""
        "component": "sensor",  # """One of the supported MQTT components, for instance `binary_sensor`"""
        "name": "sensor duration test",  # """Name of the sensor inside Home Assistant"""
        "unique_id": "rpi0-sensor-duration-test",
        "value_template": "{{value | int(0)}}",
        "state_class": "measurement",
    }  # """Set this to enable editing sensor from the HA ui and to integrate with a device"""

    SensorInfo = {"component": "sensor"}

    pinoutinfo = {
        "pin": 20,  # int = Field(description='GPIO pin to configure, change or read')
        "ptype": "out",  # Literal[PinType.pinout.value] = Field(default= PinType.pinout.value, description='The functional type of the pin like in(put) or out(put).')
        "initial": 0,  # int = Field(default= 0, description='The initial output value of the pin at the time it is created.')
        "active_state": True,  # bool = Field(default= False, description='If True, when the software state is HIGH, the hardware pin is HIGH. If False, the hardware output is reversed')
        "value": 0,  # int  | None = Field(default= None, description='The output value of the pin that is currently desired.')
        # "password": "ok",  #str | None = Field(default= None, description='An optional safety layer to prevent unwanted activation of a pin. ATTENTION! Do not use your daily passwords for (online) accounts as this api has no https and no encription.')
        "blink": 1,  # int | None = Field(default= None, description='The blink time of the output once for this number of seconds. Note it uses the previous set value to start from, the value of this call will be ignored.')
    }
    pinininfo = {
        "pin": 21,  # int = Field(description='GPIO pin to configure, change or read')
        "ptype": "count",  #  Literal[PinType.pinin.value] = Field(default= PinType.pinin.value, description='The functional type of the pin like in(put) or out(put).')
        "active_state": True,  #  bool = Field(default= True, description='If True, when the hardware pin state is HIGH, the software pin is HIGH. If False, the input polarity is reversed')
        "pull_up": False,  #  bool = Field(default= True, description='If True, the pin will be pulled high with an internal resistor. If False (the default), the pin will be pulled low.')
        "when_activated": True,  # bool = Field(default= True, description='If True, count on rising edge events.')
        "when_deactivated": True,  # bool = Field(default= True, description='If True, count on falling edge events.')
        "scaling_factor": 1.0,  # float = Field(default= 1.0, description='Reported total is count_total / scaling_factor.')
        "webhook": None,  #  str | None = Field(default= None, description='Endpoint in Home assistant to send state changes to at the moment they occure.')
    }

    binding_auto_increase = {
        "auto_increase$state": {
            "start": {"t_0": {"to": "waiting"}},
            "waiting": {
                "timeout1": {
                    "all": [{"m": {"timeout": "timeout1"}}],
                    "to": "waiting",
                    "run": [
                        {
                            "timer": {
                                "name": "timeout1",
                                "action": "start",
                                "seconds": 120,
                            }
                        },
                        {
                            "action": {
                                "unique_id": "20",
                                "call": "blink",
                                "args": [{"name": "blink", "value": 60}],
                            }
                        },
                    ],
                },
            },
        }
    }

    binding_to_sensor = {
        "pin_20_to_sensor_test": {
            "p_on": {
                "all": [
                    {"m": {"$and": [{"unique_id": "21"}, {"$ex": {"payload": 1}}]}}
                ],
                "run": {
                    "action": {
                        "unique_id": "rpi0-sensor-duration-test",
                        "call": "set_state",
                        "args": [{"name": "state", "value": "$m.payload"}],
                    }
                },
            },
        }
    }

    dgb.client.publish(
        topic="config/rpi28/devices/test",
        payload=json.dumps(
            {
                "Devices": [
                    {"EntityInfo": EntityInfo | SensorInfo},
                ],
                "Pins": [{"PinInfo": pinoutinfo}, {"PinInfo": pinininfo}],
                "Bindings": [
                    {"BindInfo": binding_to_sensor},
                    {"BindInfo": binding_auto_increase},
                ],
            }
        ),
    )
    cmd = "post"
    payload = {"rulesetname": "auto_increase", "timeout": "timeout1"}
    threading.Timer(3, dgb.dgb_context.put_to_binder_queue, args=(cmd, payload)).start()

    dgb.run_forever()


if __name__ == "__main__":
    main()
