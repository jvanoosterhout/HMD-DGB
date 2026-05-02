#!/usr/bin/env python
# encoding: utf-8
"""
MQTT client to control Raspberry GPIO pins, primarily for Home Assistant.

Jeroen van Oosterhout
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Optional

import psutil
import pkg_resources
import paho.mqtt.client as mqtt
from gpiozero import CPUTemperature
from pydantic import ValidationError
from ha_mqtt_discoverable import Settings, DeviceInfo, sensors

from DGB.DeviceKeeper import DeviceKeeper
from DGB.PinKeeper import PinKeeper
from DGB.PinModels import PinModel
from DGB.Binder import Binder
from DGB.DGBContext import DGBContext


class DGBMQTT:
    def __init__(
        self,
        name: str,
        broker: str,
        port: int = 1883,
        topic: Optional[str] = None,
        username: str = "me",
        password: str = "secret",
    ) -> None:
        self.name = name
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password

        self.config_topic = topic or f"config/{name}/devices/"
        self.client_id = f"dgb-{name}"

        self.logger = logging.getLogger(f"DGBMQTT[{name}]")
        self.logger.info("Starting DGBMQTT")

        self.shutdown_event = threading.Event()

        # Core context
        self.dgb_context = DGBContext()
        self.devicekeeper = DeviceKeeper(None, dgb_context=self.dgb_context)
        self.pinkeeper = PinKeeper(dgb_context=self.dgb_context)
        self.binder = Binder(dgb_context=self.dgb_context)

        # MQTT
        self.client: mqtt.Client = self._create_mqtt_client()
        self.mqtt_settings = Settings.MQTT(client=self.client)
        self.devicekeeper.mqtt_settings = self.mqtt_settings

        # Sensors
        self._init_system_sensors()

        self.sensor_thread = threading.Thread(
            target=self._system_sensor_loop,
            name="system-sensors",
            daemon=True,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.logger.info("Starting runtime")
        self.binder.start_event_dispatcher()
        self.client.loop_start()
        self.sensor_thread.start()

    def stop(self) -> None:
        if self.shutdown_event.is_set():
            return

        self.logger.info("Stopping DGBMQTT")
        self.shutdown_event.set()

        self.client.unsubscribe(self.config_topic + "#")
        self.client.loop_stop()
        self.client.disconnect()

        self.dgb_context.put_to_binder_queue("shutdown", {})

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def run_forever(self) -> None:
        self.start()
        self.logger.info("Runtime started, entering main loop")

        try:
            # Blokkeer de main thread totdat shutdown_event wordt gezet
            self.shutdown_event.wait()
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received")
        finally:
            self.stop()
            self.logger.info("Runtime stopped")

    # ------------------------------------------------------------------
    # MQTT setup
    # ------------------------------------------------------------------

    def _create_mqtt_client(self) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )

        client.username_pw_set(self.username, self.password)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        # client.on_disconnect = self._on_disconnect

        client.will_set(
            f"sys/{self.name}/status",
            payload="offline",
            qos=0,
            retain=True,
        )

        client.connect(self.broker, self.port)
        client.publish(f"sys/{self.name}/status", "online", retain=True)
        client.subscribe(self.config_topic + "#", qos=1)

        return client

    def _on_connect(self, client, userdata, flags, rc, properties):
        self.logger.info("Connected to MQTT broker (rc=%s)", rc)

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties):
        self.logger.info("Subscribed (mid=%s qos=%s)", mid, granted_qos)

    def _on_message(self, client, userdata, msg):
        self.logger.info("Message received on %s", msg.topic)

        if self.config_topic not in msg.topic:
            return

        payload = json.loads(msg.payload.decode())

        self._handle_devices(payload)
        self._handle_pins(payload)
        self._handle_bindings(payload)

    def _on_disconnect(
        self,
        client,
        userdata,
        rc,
        *,
        first_reconnect_delay: int = 10,
        reconnect_rate: int = 2,
        max_reconnect_count: int = 10_000,
        max_reconnect_delay: int = 600,
    ) -> None:
        """MQTT disconnect callback with bounded exponential backoff reconnect.

        Stops trying when:
        - reconnect succeeds
        - max_reconnect_count is reached
        - shutdown_event is set (graceful stop)
        """
        self.logger.info("Disconnected from MQTT (rc=%s)", rc)

        reconnect_count = 0
        reconnect_delay = first_reconnect_delay

        while (
            reconnect_count < max_reconnect_count and not self.shutdown_event.is_set()
        ):
            self.logger.info("Reconnecting in %s seconds...", reconnect_delay)

            # shutdown-aware sleep (so stop() can interrupt wait)
            self.shutdown_event.wait(reconnect_delay)
            if self.shutdown_event.is_set():
                break

            try:
                client.reconnect()
                self.logger.info("Reconnected successfully.")
                return
            except Exception as err:
                # keep as warning: it's recoverable, but worth surfacing
                self.logger.warning("Reconnect failed (%s). Retrying...", err)

            reconnect_delay = min(reconnect_delay * reconnect_rate, max_reconnect_delay)
            reconnect_count += 1

        if self.shutdown_event.is_set():
            self.logger.info("Reconnect loop stopped due to shutdown request.")
        else:
            self.logger.error(
                "Reconnect failed after %s attempts. Giving up.", reconnect_count
            )

    # ------------------------------------------------------------------
    # Payload handlers
    # ------------------------------------------------------------------

    def _handle_devices(self, payload: dict) -> None:
        for dev in payload.get("Devices", []):
            self.devicekeeper.new_device(dev)

    def _handle_pins(self, payload: dict) -> None:
        for pin in payload.get("Pins", []):
            try:
                pin_model = PinModel(pin["PinInfo"])
                self.pinkeeper.SetPin(pin_model)
            except ValidationError as e:
                self.logger.warning("Invalid pin model: %s", e)

    def _handle_bindings(self, payload: dict) -> None:
        for bind in payload.get("Bindings", []):
            self.logger.info("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            self.logger.info(bind["BindInfo"])
            self.binder.new_binding(bind["BindInfo"])

    # ------------------------------------------------------------------
    # System sensors
    # ------------------------------------------------------------------

    def _init_system_sensors(self) -> None:
        ip = self._get_ip()

        device_info = DeviceInfo(
            name=f"{self.name} main device",
            identifiers=f"dgb-{self.name}",
            model="HMD-DGB",
            manufacturer="J van Oosterhout",
            sw_version=pkg_resources.get_distribution(
                "ha-mqtt-discoverable-device-gpio-binder"
            ).version,
            configuration_url=ip,
        )

        self.cpu_temp = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="CPU temperature",
                    unit_of_measurement="°C",
                    device_class="temperature",
                    unique_id=f"{self.name}_cpu_temp",
                    device=device_info,
                ),
            )
        )

        self.uptime = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="Uptime",
                    unit_of_measurement="h",
                    device_class="duration",
                    unique_id=f"{self.name}_uptime",
                    device=device_info,
                ),
            )
        )

        self.cpu_usage = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="CPU usage",
                    unit_of_measurement="%",
                    unique_id=f"{self.name}_cpu_usage",
                    device=device_info,
                ),
            )
        )

        self.mem_usage = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="Memory usage",
                    unit_of_measurement="%",
                    unique_id=f"{self.name}_mem_usage",
                    device=device_info,
                ),
            )
        )

    def _system_sensor_loop(self) -> None:
        self.logger.info("System sensor loop started")
        while not self.shutdown_event.is_set():
            self.cpu_temp.set_state(CPUTemperature().temperature)
            self.uptime.set_state(time.monotonic() / 3600)
            self.cpu_usage.set_state(psutil.cpu_percent(interval=1))
            self.mem_usage.set_state(psutil.virtual_memory().percent)
            self.shutdown_event.wait(60)
        self.logger.info("System sensor loop stopped")

    @staticmethod
    def _get_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
