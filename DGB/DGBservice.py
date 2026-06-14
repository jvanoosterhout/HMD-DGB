#
#    Copyright 2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#
#    MQTT client to control Raspberry GPIO pins, primarily for Home Assistant.

from __future__ import annotations

import json
import logging
import threading
from typing import Optional
import argparse

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from ha_mqtt_discoverable import Settings

from DGB.DeviceKeeper import DeviceKeeper
from DGB.PinKeeper import PinKeeper
from DGB.PinModels import PinModel
from DGB.Binder import Binder
from DGB.DGBContext import DGBContext
from DGB.SystemDevices import SystemDevices


class DGBservice:
    def __init__(
        self,
        name: str,
        broker: str,
        port: int = 1883,
        topic: Optional[str] = None,
        username: str = "me",
        password: str = "secret",
        location: str = "home",
    ) -> None:
        self.name = name
        self.location = location
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
        self.pinkeeper = PinKeeper(dgb_context=self.dgb_context)
        self.binder = Binder(dgb_context=self.dgb_context)

        # MQTT
        self.client: mqtt.Client = self._create_mqtt_client()
        self.mqtt_settings = Settings.MQTT(client=self.client)

        # System devices (platform + app) - create before DeviceKeeper
        self.system_devices = SystemDevices(
            mqtt_settings=self.mqtt_settings,
            dgb_context=self.dgb_context,
            device_name=name,
            location=self.location,
            dgb_restart=self.restart,  # Pass reference to restart callback
        )
        self.system_devices.create_devices()

        # User-defined devices (from config topic)
        self.devicekeeper = DeviceKeeper(
            self.mqtt_settings, dgb_context=self.dgb_context
        )

        # Sensor update loop
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

    def _set_all_unavailable(self):
        self.logger.info("test")
        for unique_id, device_obj in list(self.dgb_context._devices_objects.items()):
            try:
                if device_obj._settings.manual_availability:
                    self.logger.info(device_obj.availability_topic)
                    self.client.publish(device_obj.availability_topic, "offline")
                    self.logger.info("Setting device %s unavailable", unique_id)
            except Exception as e:
                self.logger.warning("Error unpublishing devices: %s", e)

    def run_forever(self) -> None:
        self.start()
        self.logger.info("Runtime started, entering main loop")

        try:
            # Blokkeer de main thread totdat shutdown_event wordt gezet
            self.shutdown_event.wait()
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received")
        finally:
            self._set_all_unavailable()
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
            self.logger.info(bind["BindInfo"])
            self.binder.new_binding(bind["BindInfo"])

    # ------------------------------------------------------------------
    # App control (restart)
    # ------------------------------------------------------------------

    def restart(self) -> None:
        """
        Stop the DGB app, restart is handeled by systemd.

        """
        self.logger.info("Restarting DGB app - full reinitialization and cleanup")

        # Step 4: Unpublish devices from HA
        # Send empty retained messages to MQTT discovery topics
        self.logger.info("Unpublishing devices from Home Assistant")
        for unique_id, device_obj in list(self.dgb_context._devices_objects.items()):
            try:
                self.logger.info(device_obj.config_topic)
                self.client.publish(device_obj.config_topic, "")
                self.logger.info("Cleared device %s from registry", unique_id)
            except Exception as e:
                self.logger.warning("Error unpublishing devices: %s", e)

        self.stop()

    # ------------------------------------------------------------------
    # System sensor updates
    # ------------------------------------------------------------------

    def _system_sensor_loop(self) -> None:
        """Update system sensor values periodically (every 60 seconds)."""
        self.logger.info("System sensor loop started")
        while not self.shutdown_event.is_set():
            self.system_devices.update_sensor_values()
            self.shutdown_event.wait(60)
        self.logger.info("System sensor loop stopped")


def main():
    parser = argparse.ArgumentParser(description="Start DGB MQTT service")
    parser.add_argument("--name", required=True, help="Device name")
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT port")
    parser.add_argument("--topic", default=None, help="MQTT topic")
    parser.add_argument("--username", default="me", help="MQTT username")
    parser.add_argument("--password", default="secret", help="MQTT password")
    parser.add_argument("--location", default="home", help="Device location")

    args = parser.parse_args()

    service = DGBservice(
        name=args.name,
        broker=args.broker,
        port=args.port,
        topic=args.topic,
        username=args.username,
        password=args.password,
        location=args.location,
    )

    # start service if needed
    service.run_forever()


if __name__ == "__main__":
    main()
