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

import argparse
import json
import logging
import threading
import time

import paho.mqtt.client as mqtt
from ha_mqtt_discoverable import Settings
from pydantic import ValidationError

from DGB.Binder import Binder
from DGB.DeviceKeeper import DeviceKeeper
from DGB.DGBContext import DGBContext
from DGB.PinKeeper import PinKeeper
from DGB.PinModels import PinModel
from DGB.SetStateResolver import SetStateResolver
from DGB.StartupPolicy import ErrorStatePolicy, RuntimePhase
from DGB.StartupStateInitializer import StartupStateInitializer
from DGB.SystemDevices import SystemDevices


class DGBservice:
    def __init__(
        self,
        name: str,
        broker: str,
        username: str,
        password: str,
        location: str,
        port: int = 1883,
        topic: str | None = None,
        system_sensor_update_rate: int = 60,
    ) -> None:
        self.name = name
        self.location = location
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.system_sensor_update_rate = system_sensor_update_rate
        self.state_resolver = SetStateResolver()

        self._temp_subscription_lock = threading.Lock()
        self._temp_subscription_active = False
        self._temp_subscription_last_activity = time.monotonic()

        self.client_id = f"dgb-{self.name}"

        self.logger = logging.getLogger(f"DGBservice[{self.name}]")
        self.logger.info("Starting DGBservice")

        self.shutdown_event = threading.Event()

        # create context keeper
        self.dgb_context = DGBContext()
        self.dgb_context.availability_topic_ns = f"sys/{self.name}/status"

        # MQTT
        self.config_topic = topic or f"config/{self.name}/devices/"
        self.startup_policy_topic = topic or f"config/{self.name}/startup-policy"
        self.state_retain_topic_prefix = f"config/{self.name}/states/"
        self.client: mqtt.Client = self._create_mqtt_client()
        self.mqtt_settings = Settings.MQTT(client=self.client)

        self.dgb_context.configure_retained_state_publishing(
            prefix=self.state_retain_topic_prefix,
            publish_fn=self.client.publish,
        )
        # Core context
        self.pinkeeper = PinKeeper(dgb_context=self.dgb_context)
        self.binder = Binder(dgb_context=self.dgb_context)
        self.devicekeeper = DeviceKeeper(
            self.mqtt_settings, dgb_context=self.dgb_context
        )
        self.startup_state = StartupStateInitializer(
            dgb_context=self.dgb_context,
            state_resolver=self.state_resolver,
            state_retain_topic_prefix=self.state_retain_topic_prefix,
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

        # start phase 1: preload
        # self.startup_state.handle_subscription_to_retained_state_topic()

        self.handle_temp_subscription(self.startup_policy_topic)
        while self._temp_subscription_active:
            time.sleep(0.5)
        self.handle_temp_subscription(
            f"{self.state_retain_topic_prefix}#", quiet_seconds=1
        )
        while self._temp_subscription_active:
            time.sleep(0.5)
        # state phase 2-5: config-create-apply-live
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

    def handle_temp_subscription(
        self, topic: str, timeout_seconds: float = 1.0, quiet_seconds: float = 0.5
    ):
        """Subscribe to retained state topics until the preload window becomes quiet or expires."""
        now = time.monotonic()

        with self._temp_subscription_lock:
            self._temp_subscription_active = True
            self._temp_subscription_last_activity = now

        try:
            self.client.subscribe(topic, qos=1)
            self.logger.info("Temporary subscription window opened for %s", topic)

            deadline = now + timeout_seconds
            while time.monotonic() < deadline:
                with self._temp_subscription_lock:
                    elapsed = time.monotonic() - self._temp_subscription_last_activity
                if elapsed >= quiet_seconds:
                    break
                time.sleep(0.01)
        finally:
            self.client.unsubscribe(topic)
            with self._temp_subscription_lock:
                self._temp_subscription_active = False
            self.logger.info("Temporary subscription window closed for %s", topic)

    def handle_startup_policy(self, payload) -> None:

        with self._temp_subscription_lock:
            self._temp_subscription_last_activity = time.monotonic()

        # Validate startup policy and extract startup state values.
        raw_startup_policy = self.startup_state.get_dict(payload, "startup_policy")
        self.dgb_context.config_cycle.set_startup_policy(raw_startup_policy)

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

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        self.logger.info("Message received on %s", msg.topic)
        try:
            raw_payload = msg.payload.decode()
        except UnicodeDecodeError as exc:
            raise ValueError("retained state payload is not valid UTF-8") from exc

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON: {e.msg}")
            self.logger.error(f"Line: {e.lineno}, column: {e.colno}, char: {e.pos}")
            return

        if self.startup_state.is_retained_state_topic(msg.topic):
            self.startup_state.handle_retained_state_message(payload, msg.topic)
            return

        if self.startup_policy_topic in msg.topic:
            self.handle_startup_policy(payload)
            return

        if self.config_topic in msg.topic:
            self.dgb_context.put_to_config_queue(
                "apply", payload, source_topic=msg.topic
            )
            return

    def config_dispatcher(self) -> None:
        while True:
            msg = self.dgb_context.config_queue.get()

            if msg.cmd == "shutdown":
                self.logger.info("Config dispatcher shutdown requested")
                self.dgb_context.config_queue.task_done()
                break

            if msg.cmd == "apply":
                if self._should_dispatch_config():
                    self._run_config_apply_cycle(msg.payload, msg.source_topic)
                self.dgb_context.config_queue.task_done()

    def _should_dispatch_config(self) -> bool:
        """Return whether the current queued configuration may start a cycle."""
        phase = self.dgb_context.config_cycle.get_phase()
        if phase == RuntimePhase.LIVE:
            return True

        if phase != RuntimePhase.ERROR:
            self.logger.warning(
                "Configuration not dispatched while config cycle is in %s phase",
                phase,
            )
            return False

        if (
            self.dgb_context.config_cycle.startup_policy.error_state_policy
            == ErrorStatePolicy.WARN
        ):
            self.logger.warning(
                "Previous config cycle had an error; proceeding with next config due to "
                "error_state_policy=warn"
            )
            return True

        self.logger.error(
            "Previous config cycle had an error; new configuration dispatched blocked due to error_state_policy=block"
        )
        return False

    # phase 2 - 5
    def _run_config_apply_cycle(
        self, payload: dict, source_topic: str | None = None
    ) -> None:
        # Phase 2: configure startup policy and confic checks
        # Idempotency check: skip if this exact payload was already applied.
        payload_hash = self.dgb_context.config_cycle.compute_payload_hash(payload)
        if self.dgb_context.config_cycle.payload_already_applied(payload_hash):
            self.logger.info("Configuration already applied, skiping this one")
            return
        self.dgb_context.config_cycle.record_payload_hash(payload_hash)

        # Phase 3: creating phase
        try:
            cycle_id = self.dgb_context.config_cycle.begin_cycle()
            self.logger.info("Config cycle %s entered creation phase", cycle_id)
            self._handle_devices(payload)
            self._handle_pins(payload)
            self._handle_bindings(payload)
        except Exception:
            self.dgb_context.config_cycle.set_phase(RuntimePhase.ERROR)
            self._blocked_config_topic = source_topic
            self.logger.exception(
                "Config cycle %s failed at create phase; runtime phase set to error",
                cycle_id,
            )
            self._handle_blocked_cycle()
            return

        # phase 4: record retained state needs and preset state values
        if "state_initialization" in payload:
            state_initialization = self.startup_state.get_dict(
                payload, "state_initialization"
            )
            self.startup_state.register_retained_state_need(state_initialization)
            self.startup_state.register_preset_states(state_initialization)

        # Phase 5: apply preset and retained values
        try:
            self.dgb_context.config_cycle.set_phase(RuntimePhase.APPLY)
            self.logger.info("Config cycle %s entered apply phase", cycle_id)
            self.startup_state.apply_startup_states()
        except Exception:
            self.dgb_context.config_cycle.set_phase(RuntimePhase.ERROR)
            self._blocked_config_topic = source_topic
            self.logger.exception(
                "Config cycle %s failed at apply phase; runtime phase set to error",
                cycle_id,
            )
            self._handle_blocked_cycle()
            return

        # Phase 5: Transition to live (and trigger initial values to flow though bindings).
        self.dgb_context.config_cycle.set_phase(RuntimePhase.LIVE)
        self.dgb_context.config_cycle.complete_cycle(cycle_id)
        self._blocked_config_topic = None
        self.logger.info("Config cycle %s entered live phase", cycle_id)

    def _handle_blocked_cycle(self) -> None:
        """Perform recovery required by the failed cycle's error-state policy."""
        if (
            self.dgb_context.config_cycle.startup_policy.error_state_policy
            == ErrorStatePolicy.CLEAR_AFFECTED_CONFIG_AND_RESTART
        ):
            if self._blocked_config_topic is None:
                self.logger.error(
                    "Cannot clear failed config: its source topic is unknown"
                )
                return
            self.client.publish(
                self._blocked_config_topic, payload=None, qos=1, retain=True
            )
            self.logger.error(
                "Cleared failed retained config on %s", self._blocked_config_topic
            )
            self.restart()
        if (
            self.dgb_context.config_cycle.startup_policy.error_state_policy
            == ErrorStatePolicy.REMOVE_AFFECTED_DEVICE_AND_BINDING
        ):
            self.logger.error(
                "Cannot remove affected devices and bindings as policy is not implemeneted yet."
            )
            return

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
            for unique_id, obj in self.dgb_context.DGB_objects.items():
                try:
                    if not hasattr(obj.dgb_obj, "config_topic"):
                        continue
                    self.client.publish(obj.dgb_obj.config_topic, payload=None)
                    self.logger.info("Cleared device %s from registry", unique_id)
                    # self.dgb_context.remove_object(unique_id)
                except (AttributeError, OSError, RuntimeError, ValueError) as e:
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
