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
#    Startup-state initialization helpers for DGBservice.

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from DGB.ActionArguments import ArgumentBuilder
from DGB.DGBContext import DGBContext
import paho.mqtt.client as mqtt


class StartupStateInitializer:
    def __init__(
        self,
        dgb_context: DGBContext,
        mqtt_client: mqtt.Client,
        arg_builder: ArgumentBuilder,
        state_retain_topic_prefix: str,
        preload_quiet_seconds: float = 0.5,
        preload_timeout_seconds: float = 1.0,
    ) -> None:
        self.dgb_context = dgb_context
        self.mqtt_client = mqtt_client
        self.logger = logging.getLogger("StartupStateInitializer")
        self.arg_builder = arg_builder
        self.state_shadow_prefix = state_retain_topic_prefix
        self.preload_quiet_seconds = preload_quiet_seconds
        self.preload_timeout_seconds = preload_timeout_seconds
        self._preload_lock = threading.Lock()
        self._preload_active = False
        self._preload_last_activity = time.monotonic()

    # ------------------------------------------------------------------
    # 1.1) Preload Values from MQTT: helpers
    # ------------------------------------------------------------------

    def is_state_shadow_topic(self, topic: str) -> bool:
        return topic.startswith(self.state_shadow_prefix)

    def _unique_id_from_retained_state_topic(self, topic: str) -> str | None:
        suffix = topic[len(self.state_shadow_prefix) :].strip("/")
        if not suffix:
            return None
        unique_id, *_ = suffix.split("/", 1)
        return unique_id if unique_id else None

    def _state_name_from_retained_state_topic(self, topic: str) -> str:
        suffix = topic[len(self.state_shadow_prefix) :].strip("/")
        if "/" not in suffix:
            return "payload"
        return suffix.split("/", 1)[1] or "payload"

    def _decode_retained_state_payload(self, payload: bytes) -> Any:
        raw = payload.decode()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # ------------------------------------------------------------------
    # 1.2)Preload Values from MQTT: message handling
    # ------------------------------------------------------------------

    def handle_subscription_to_retaind_state_topic(self) -> None:
        wildcard_topic = f"{self.state_shadow_prefix}#"
        now = time.monotonic()
        with self._preload_lock:
            self._preload_active = True
            self._preload_last_activity = now

        self.mqtt_client.subscribe(wildcard_topic, qos=1)
        self.logger.info("Preloading retained state from %s", wildcard_topic)

        deadline = now + self.preload_timeout_seconds
        try:
            while time.monotonic() < deadline:
                with self._preload_lock:
                    elapsed = time.monotonic() - self._preload_last_activity
                if elapsed >= self.preload_quiet_seconds:
                    break
                time.sleep(0.01)
        finally:
            self.mqtt_client.unsubscribe(wildcard_topic)
            with self._preload_lock:
                self._preload_active = False
            self.logger.info("Retained preload window closed for %s", wildcard_topic)

    def handle_retaind_state_message(self, msg) -> None:
        unique_id = self._unique_id_from_retained_state_topic(msg.topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid state shadow topic: %s", msg.topic)
            return

        decoded_payload = self._decode_retained_state_payload(msg.payload)
        state_name = self._state_name_from_retained_state_topic(msg.topic)
        self.dgb_context.record_retained_state(
            unique_id=unique_id,
            state_name=state_name,
            value=decoded_payload,
        )

        if getattr(msg, "retain", False):
            with self._preload_lock:
                if self._preload_active:
                    self._preload_last_activity = time.monotonic()

        self.logger.info(
            "Stored retained shadow value for %s from %s (%s)",
            unique_id,
            msg.topic,
            state_name,
        )

    # ------------------------------------------------------------------
    # 2.1) Load startup config: register retaind required
    # ------------------------------------------------------------------

    def register_retained_state_need(self, raw_startup_policy: dict):
        # raw_atartup_policy has
        # "retain_state": [{"unique_id": "id", "name": ["state_name"]}]
        retain_devices = self.get_list(raw_startup_policy, "retain_state")
        for retain_device in retain_devices:
            state_names = self.get_list(retain_device, "name")
            self.dgb_context.record_retained_state_need(
                retain_device.get("unique_id"), state_names
            )

    def get_list(
        self,
        raw_startup_policy: dict[str, list],
        key: str,
    ) -> list:
        """Parse a bucket."""
        raw_list = raw_startup_policy.get(key, [])
        if not isinstance(raw_list, list):
            raise ValueError(
                f"Key {key} in given dict does not contain a list, got {type(raw_list).__name__!r}"
            )
        return raw_list

    def get_dict(
        self,
        raw_startup_policy: dict[str, dict],
        key: str,
    ) -> dict:
        """Parse a bucket."""
        raw_list = raw_startup_policy.get(key, {})
        if not isinstance(raw_list, dict):
            raise ValueError(
                f"Key {key} in given dict does not contain a dict, got {type(raw_list).__name__!r}"
            )
        return raw_list

    # ------------------------------------------------------------------
    # 2.2) Load startup config: save preset values + state name per unique_id
    # ------------------------------------------------------------------

    def register_preset_states(self, raw_sources: dict) -> None:
        """
        Parse preset state entries.

        For this DGB stage, preset startup values are restricted to:
        - call: "set_state"
        - args: [{"name": "state_name", "value": ...}, {"name": "value", "value": ...}]

        """
        raw_preset = raw_sources.get("preset_value", [])
        if isinstance(raw_preset, dict):
            raw_list = [raw_preset]
        elif isinstance(raw_preset, list):
            raw_list = raw_preset
        else:
            raise ValueError(
                "Preset_value expected a list or dict, "
                f"got {type(raw_preset).__name__!r}"
            )

        for raw in raw_list:
            unique_id = raw.get("unique_id")
            call = raw.get("call")
            args_list = self.get_list(raw, "args")
            if call != "set_state":
                raise ValueError("preset_value 'call' must be 'set_state'")

            for args in args_list:
                state_name, state = self._parse_state_args(args)
                self.dgb_context.record_preset_value(unique_id, state_name, state)

    def _parse_state_args(self, args: dict[str, Any]) -> tuple[str, Any]:
        """Validate and normalize set_state startup args into (state_name, value)."""
        state_name_arg = args.get("name", None)
        value_arg = args.get("value", None)
        if not isinstance(state_name_arg, str):
            raise ValueError("preset_value arg 'name' must be str entries")
        if state_name_arg is None or value_arg is None:
            raise ValueError(
                "preset_value 'name' or 'value' are not or incorrect defined"
            )
        return state_name_arg, value_arg

    # ------------------------------------------------------------------
    # 3) Know What To Retain And Apply To Device
    # ------------------------------------------------------------------

    def apply_startup_state(self) -> None:
        startup_snapshot = self.dgb_context.get_startup_state_snapshot()
        self._apply_state_values(startup_snapshot)

    def _apply_state_values(
        self,
        startup_snapshot: list[tuple[str, dict[str, Any], bool, dict[str, Any]]],
    ) -> None:
        for (
            unique_id,
            preset_values,
            retain_required,
            retained_values,
        ) in startup_snapshot:
            self._apply_state_map(unique_id, preset_values, source_label="preset_value")
            if retain_required:
                self._apply_state_map(
                    unique_id, retained_values, source_label="retain_state"
                )

    def _apply_state_map(
        self,
        unique_id: str,
        state_values: dict[str, Any],
        source_label: str,
    ) -> None:
        if not state_values:
            if source_label == "retain_state":
                self.logger.info(
                    "Startup source for %s retained missing; no startup state applied",
                    unique_id,
                )
            return

        applied_any = False
        for state_name, value in state_values.items():
            if state_name == "payload":
                self.logger.warning(
                    "%s state for %s ignored: legacy payload topic has no state name",
                    source_label,
                    unique_id,
                )
                continue

            action_payload = {
                "call": "set_state",
                "args": [
                    {"name": "state_name", "value": state_name},
                    {"name": "value", "value": value},
                ],
            }
            if self._apply_action_payload(
                unique_id=unique_id, action_payload=action_payload
            ):
                applied_any = True

        if applied_any and source_label == "retain_state":
            self.logger.info(
                "Startup source for %s resolved from retained state", unique_id
            )

    def _apply_action_payload(
        self,
        unique_id: str,
        action_payload: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(action_payload, dict):
            self.logger.warning(
                "Configured default for %s ignored: action payload must be a dict",
                unique_id,
            )
            return False

        functions = self.dgb_context.get_functions(unique_id)
        if not functions:
            self.logger.warning(
                "Configured default for %s ignored: no registered functions",
                unique_id,
            )
            return False

        try:
            resolved = self.arg_builder.resolve_callable_action(
                action_payload={"unique_id": unique_id, **action_payload},
                function_resolver=lambda uid, call: functions.get(call),
                source_label="preset_value",
                allow_context_refs=False,
            )
        except (ValueError, KeyError) as e:
            self.logger.warning(
                "Configured default for %s ignored: %s",
                unique_id,
                str(e),
            )
            return False

        call_args = self.arg_builder.build_call_args(resolved.arg_defs, {})
        resolved.action_fn(**call_args)
        self.logger.info(
            "Applied configured default via action call for %s (%s)",
            resolved.unique_id,
            resolved.call_name,
        )
        return True
