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
from DGB.ActionArguments import ArgumentBuilder
from DGB.DGBContext import DGBContext
from DGB.StartupStateInitializer import StartupStateInitializer
from DGB.StartupPolicy import (
    StartupPolicy,
    parse_startup_policy,
    resolve_state_sources,
)
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
        system_sensor_update_rate: int = 60,
    ) -> None:
        self.name = name
        self.location = location
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.system_sensor_update_rate = system_sensor_update_rate
        self.arg_builder = ArgumentBuilder()

        self.client_id = f"dgb-{self.name}"

        self.logger = logging.getLogger(f"DGBservice[{self.name}]")
        self.logger.info("Starting DGBservice")

        self.shutdown_event = threading.Event()

        # create context keeper
        self.dgb_context = DGBContext()
        self.dgb_context.availability_topic_ns = f"sys/{self.name}/status"

        # MQTT
        self.config_topic = topic or f"config/{self.name}/devices/"
        self.state_shadow_prefix = f"state/{self.name}/"
        self.client: mqtt.Client = self._create_mqtt_client()
        self.mqtt_settings = Settings.MQTT(client=self.client)

        # Core context
        self.pinkeeper = PinKeeper(dgb_context=self.dgb_context)
        self.binder = Binder(dgb_context=self.dgb_context)
        self.devicekeeper = DeviceKeeper(
            self.mqtt_settings, dgb_context=self.dgb_context
        )
        self.startup_state = StartupStateInitializer(
            dgb_context=self.dgb_context,
            mqtt_client=self.client,
            logger=self.logger,
            arg_builder=self.arg_builder,
            state_shadow_prefix=self.state_shadow_prefix,
        )

        # System devices (platform + app) - create before DeviceKeeper
        self.system_devices = SystemDevices(
            mqtt_settings=self.mqtt_settings,
            dgb_context=self.dgb_context,
            device_name=self.name,
            location=self.location,
            dgb_restart=self.restart,  # Pass reference to restart callback
        )
        self.system_devices.create_devices()

        # Sensor update loop
        self.sensor_thread = threading.Thread(
            target=self._system_sensor_loop,
            name="system-sensors",
            daemon=True,
        )
        self.config_thread = threading.Thread(
            target=self.config_dispatcher,
            name="config-dispatcher",
            daemon=True,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.logger.info("Starting runtime")
        self.binder.start_event_dispatcher()
        self.config_thread.start()
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
        self.dgb_context.put_to_config_queue("shutdown", {})

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def _set_unavailable(self):
        self.client.publish(
            self.dgb_context.availability_topic_ns,
            payload="offline",
            qos=1,
            retain=True,
        )

    def run_forever(self) -> None:
        self.start()
        self.logger.info("Runtime started, entering main loop")

        try:
            # Blokkeer de main thread totdat shutdown_event wordt gezet
            self.shutdown_event.wait()
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received")
        finally:
            self._set_unavailable()
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
            self.dgb_context.availability_topic_ns,
            payload="offline",
            qos=1,
            retain=True,
        )
        client.connect(
            self.broker, self.port, keepalive=self.system_sensor_update_rate + 10
        )
        client.subscribe(self.config_topic + "#", qos=1)

        return client

    def _on_connect(self, client, userdata, flags, rc, properties):
        self.logger.info("Connected to MQTT broker (rc=%s)", rc)
        self.client.publish(
            self.dgb_context.availability_topic_ns, payload="online", qos=1, retain=True
        )

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties):
        self.logger.info("Subscribed (mid=%s qos=%s)", mid, granted_qos)

    def _on_message(self, client, userdata, msg):
        self.logger.info("Message received on %s", msg.topic)

        if self.startup_state.is_state_shadow_topic(msg.topic):
            self.startup_state.handle_state_shadow_message(msg)
            return

        if self.config_topic not in msg.topic:
            return

        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON: {e.msg}")
            self.logger.error(f"Line: {e.lineno}, column: {e.colno}, char: {e.pos}")
            return

        self.dgb_context.put_to_config_queue("apply", payload)

    def config_dispatcher(self) -> None:
        while True:
            msg = self.dgb_context.config_queue.get()

            if msg.cmd == "shutdown":
                self.logger.info("Config dispatcher shutdown requested")
                self.dgb_context.config_queue.task_done()
                break

            if msg.cmd == "apply":
                self._run_config_apply_cycle(msg.payload)
                self.dgb_context.config_queue.task_done()

    def _run_config_apply_cycle(self, payload: dict) -> None:
        cycle_id = self.dgb_context.begin_config_apply_cycle()
        payload_hash = self.dgb_context.compute_payload_hash(payload)

        # Idempotency check: skip if this exact payload was already applied.
        if self.dgb_context.payload_already_applied(payload_hash):
            self.logger.info(
                "Config cycle %s: payload already applied (idempotent skip)",
                cycle_id,
            )
            return

        self.logger.info("Config cycle %s entered creation phase", cycle_id)

        # Parse and normalize startup_policy (Stage 2)
        startup_policy: StartupPolicy = parse_startup_policy(
            payload.get("startup_policy", {})
        )

        # Resolve winning state source per unique_id (Stage 3)
        decisions = resolve_state_sources(startup_policy.state_initialization)

        try:
            self._handle_devices(payload)
            self._handle_pins(payload)
            self._handle_bindings(payload)

            self.dgb_context.set_runtime_phase("apply")
            self.logger.info("Config cycle %s entered apply phase", cycle_id)
            self.startup_state.register_retained_subscriptions(decisions)
            self.startup_state.resolve_retained_sources(decisions)
            self.startup_state.apply_configured_defaults(decisions)
        except Exception:
            self.dgb_context.set_runtime_phase("blocked")
            self.logger.exception(
                "Config cycle %s failed; runtime phase set to blocked", cycle_id
            )
            return

        # Transition to live.
        self.dgb_context.set_runtime_phase("live")
        self.dgb_context.complete_config_cycle(cycle_id)
        self.logger.info("Config cycle %s entered live phase", cycle_id)

        # Record this payload as applied for future dedup.
        self.dgb_context.record_payload_hash(payload_hash)

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

    def restart(self, hard_restart: bool = False) -> None:
        """
        Stop the DGB app, restart is handeled by systemd.

        """
        self.logger.info("Restarting DGB app")

        # Restart the service and keep all config (inbound and outbound) info OR do a hard reset clearing all config info
        self._set_unavailable()
        if hard_restart:
            self.logger.info("Full reinitialization and cleanup")
            for unique_id, dgb_obj in self.dgb_context.iter_objects():
                try:
                    if not hasattr(dgb_obj, "config_topic"):
                        continue
                    self.client.publish(dgb_obj.config_topic, payload=None)
                    self.logger.info("Cleared device %s from registry", unique_id)
                    self.dgb_context.remove_object(unique_id)
                except Exception as e:
                    self.logger.warning("Error unpublishing devices: %s", e)
            self.client.publish(self.config_topic, payload=None)
            self.client.loop(timeout=0.5)
        self.stop()

    # ------------------------------------------------------------------
    # System sensor updates
    # ------------------------------------------------------------------

    def _system_sensor_loop(self) -> None:
        """Update system sensor values periodically (default every 60 seconds)."""
        self.logger.info("System sensor loop started")
        while not self.shutdown_event.is_set():
            self.system_devices.update_sensor_values()
            self.shutdown_event.wait(self.system_sensor_update_rate)
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
    parser.add_argument(
        "--rate", type=int, default=60, help="System sensor update rate in seconds"
    )

    args = parser.parse_args()

    service = DGBservice(
        name=args.name,
        broker=args.broker,
        port=args.port,
        topic=args.topic,
        username=args.username,
        password=args.password,
        location=args.location,
        system_sensor_update_rate=args.rate,
    )

    # start service if needed
    service.run_forever()


if __name__ == "__main__":
    main()
