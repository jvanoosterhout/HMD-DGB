#!/usr/bin/env python
# encoding: utf-8
"""
MQTT client to control Raspberry GPIO pins from anywhere but specifically Home Assistant. Including fallback option when iether of the two reboots.

Jeroen van Oosterhout, 10-12-2025
"""

import logging
import time
import psutil
from gpiozero import CPUTemperature
from DGB.DeviceKeeper import DeviceKeeper
import paho.mqtt.client as mqtt
from ha_mqtt_discoverable import Settings, DeviceInfo, sensors
import json
from DGB.PinKeeper import PinKeeper
from DGB.PinModels import PinModel
from DGB.Binder import Binder
from DGB.DGBContext import DGBContext
import pkg_resources
import socket
import threading
from pydantic import ValidationError


logging.basicConfig(level="INFO")


class Pin_mqtt:
    def __init__(
        self,
        name: str,
        broker: str = "",
        port: int = 1883,
        topic: str = None,
        username: str = "me",
        password: str = "secret",
        pin_pw_list: dict = {},
    ):
        print("test DGB pin mqtt")
        self.name = name
        self.broker = broker
        self.port = port
        if topic:
            self.config_topic = topic
        else:
            self.config_topic = f"config/{name}/devices/"
        self.client_id = f"python-mqtt-{name}"
        self.username = username
        self.password = password

        self.client = None
        self.mqtt_settings = None

        self.cpu_temp_sensor = None
        self.up_time_sensor = None
        self.cpu_percentage_sensor = None
        self.memory_usage_sensor = None

        self.logger = logging.getLogger("{}_log".format(self.name))
        self.logger.info("starting {}".format(self.name))

        self.config_brokker()

        self.dgb_context = DGBContext()
        self.devicekeeper = DeviceKeeper(
            self.mqtt_settings, dgb_context=self.dgb_context
        )
        self.pinkeeper = PinKeeper(
            pin_pw_list=pin_pw_list, dgb_context=self.dgb_context
        )
        self.binder = Binder(dgb_context=self.dgb_context)
        self.shutdown = False

        self.config_system_sensors()

    def __del__(self):
        self.shutdown = True
        self.client.unsubscribe(self.config_topic)
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("unscribed and disconnected")
        self.dgb_context.put_to_binder_queue("shutdown", {})

    def config_brokker(self):
        def on_connect(client, userdata, flags, rc, properties):
            self.logger.info("CONNACK received with code {}.".format(rc))

        def on_disconnect(client, userdata, rc):
            FIRST_RECONNECT_DELAY = 10
            RECONNECT_RATE = 2
            MAX_RECONNECT_COUNT = 10000
            MAX_RECONNECT_DELAY = 600

            self.logger.info("Disconnected with result code: {}".format(rc))
            reconnect_count, reconnect_delay = 0, FIRST_RECONNECT_DELAY
            while reconnect_count < MAX_RECONNECT_COUNT:
                self.logger.info("Reconnecting in %d seconds...", reconnect_delay)
                time.sleep(reconnect_delay)

                try:
                    client.reconnect()
                    self.logger.info("Reconnected successfully!")
                    return
                except Exception as err:
                    self.logger.info("%s. Reconnect failed. Retrying...", err)

                reconnect_delay *= RECONNECT_RATE
                reconnect_delay = min(reconnect_delay, MAX_RECONNECT_DELAY)
                reconnect_count += 1
            self.logger.info(
                "Reconnect failed after %s attempts. Exiting...", reconnect_count
            )

        def on_subscribe(client, userdata, mid, granted_qos, properties):
            self.logger.info("Subscribed: " + str(mid) + " " + str(granted_qos))

        def on_message(client, userdata, msg):
            self.logger.info("new msg recieved on topic " + msg.topic)
            if self.config_topic in msg.topic:
                payload = json.loads(msg.payload.decode())
                if "Devices" in payload:
                    for dev in payload["Devices"]:
                        self.devicekeeper.new_device(dev)
                else:
                    self.logger.warning("No Devices in payload")

                if "Pins" in payload:
                    for pin in payload["Pins"]:
                        try:
                            pin_model = PinModel(pin["PinInfo"])
                        except ValidationError as e:  # Exception as e
                            raise self.logger.warning(str(e))

                        self.logger.info(
                            "Posting new (value for) pin: {}".format(pin_model)
                        )
                        if self.pinkeeper.SetPin(pin_model):
                            self.logger.info("pin made succesfully")
                        else:
                            self.logger.info("pin creation failed")
                else:
                    self.logger.warning("No Pins in payload")
                if "Bindings" in payload:
                    for bind in payload["Bindings"]:
                        self.binder.new_binding(bind["BindInfo"])
                else:
                    self.logger.warning("No Bindings in payload")

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )
        self.client.on_connect = on_connect
        # self.client.on_disconnect = on_disconnect
        self.client.on_subscribe = on_subscribe
        self.client.on_message = on_message

        self.client.username_pw_set(self.username, self.password)
        self.client.will_set(
            "sys/{}/status".format(self.name), payload="offline", qos=0, retain=True
        )
        self.client.publish("sys/{}/status".format(self.name), "online", 0, retain=True)
        self.client.connect(self.broker, self.port)
        self.client.subscribe(self.config_topic + "#", qos=1)
        self.logger.info("subscribed to toppic {}".format(self.config_topic))

        self.mqtt_settings = Settings.MQTT(client=self.client)

    def config_system_sensors(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))

        device_info = DeviceInfo(
            name="{} main device".format(self.name),
            identifiers="device_id_{}_001".format(self.name),
            model="HMD-DGB",
            manufacturer="J van Oosterhout",
            sw_version=str(
                pkg_resources.get_distribution(
                    "ha-mqtt-discoverable-device-gpio-binder"
                ).version
            ),
            configuration_url=str(s.getsockname()[0]),
        )
        logging.info(device_info.identifiers)

        cpu_temp_info = sensors.SensorInfo(
            name="CPU temperature",
            unit_of_measurement="°C",
            device_class="temperature",
            unique_id="sensor_id_{}_cpu_temp".format(self.name),
            expire_after=360,
            device=device_info,
        )
        up_time_info = sensors.SensorInfo(
            name="System up time",
            unit_of_measurement="h",
            device_class="duration",
            unique_id="sensor_id_{}_up_time".format(self.name),
            expire_after=360,
            device=device_info,
        )
        cpu_percentage_info = sensors.SensorInfo(
            name="CPU usage",
            unit_of_measurement="%",
            unique_id="sensor_id_{}_cpu_usage".format(self.name),
            expire_after=360,
            device=device_info,
            # device_class="temperature",
        )
        memory_usage_info = sensors.SensorInfo(
            name="Memory usage",
            unit_of_measurement="%",
            unique_id="sensor_id_{}_mem_usage".format(self.name),
            expire_after=360,
            device=device_info,
            # device_class="temperature",
        )
        # Instantiate the sensor
        self.cpu_temp_sensor = sensors.Sensor(
            Settings(mqtt=self.mqtt_settings, entity=cpu_temp_info)
        )
        self.up_time_sensor = sensors.Sensor(
            Settings(mqtt=self.mqtt_settings, entity=up_time_info)
        )
        self.cpu_percentage_sensor = sensors.Sensor(
            Settings(mqtt=self.mqtt_settings, entity=cpu_percentage_info)
        )
        self.memory_usage_sensor = sensors.Sensor(
            Settings(mqtt=self.mqtt_settings, entity=memory_usage_info)
        )

    def update_system_sensors(self):
        self.logger.info("system sensor updates started")
        while True:
            if self.shutdown:
                break
            # Change the state of the sensor, publishing an MQTT message that gets picked up by HA
            self.cpu_temp_sensor.set_state(CPUTemperature().temperature)
            self.up_time_sensor.set_state(time.monotonic() / 60 / 60)
            self.cpu_percentage_sensor.set_state(psutil.cpu_percent(interval=1))
            self.memory_usage_sensor.set_state(psutil.virtual_memory().percent)
            time.sleep(60)
        self.logger.info("system sensor updates stoped")

    def run(self):
        self.binder.start_event_dispatcher()
        self.client.loop_start()
        t = threading.Thread(target=self.update_system_sensors)
        t.start()
        # while True:
        #     # self.update_system_sensors()
        #     time.sleep(60)
