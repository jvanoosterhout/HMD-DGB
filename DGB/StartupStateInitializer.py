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

import paho.mqtt.client as mqtt

from DGB.ActionArguments import ArgumentBuilder
from DGB.DGBContext import DGBContext


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
        self.retained_state_topic_prefix = state_retain_topic_prefix
        self.preload_quiet_seconds = preload_quiet_seconds
        self.preload_timeout_seconds = preload_timeout_seconds
        self._preload_lock = threading.Lock()
        self._preload_active = False
        self._preload_last_activity = time.monotonic()

    # ------------------------------------------------------------------
    # 1.1) Preload Values from MQTT: helpers
    # ------------------------------------------------------------------

    def is_state_shadow_topic(self, topic: str) -> bool:
        return topic.startswith(self.retained_state_topic_prefix)

    def _unique_id_from_retained_state_topic(self, topic: str) -> str | None:
        suffix = topic[len(self.retained_state_topic_prefix) :].strip("/")
        if not suffix:
            return None
        unique_id, *_ = suffix.split("/", 1)
        return unique_id if unique_id else None

    def _call_name_from_retained_state_topic(self, topic: str) -> str:
        suffix = topic[len(self.retained_state_topic_prefix) :].strip("/")
        if "/" not in suffix:
            return "set_state"
        return suffix.split("/", 1)[1] or "set_state"

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
        wildcard_topic = f"{self.retained_state_topic_prefix}#"
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
        """
        Handle the retained state message by saving it in DGBcontext.

        Args:
            msg: MQTT msg with json payload. Its topic should have the shape of retained_state_topic_prefix/unique_id/call_name. Its payload should be in the shape of {"args": [{"state_name": "Any"}]}

        """
        unique_id = self._unique_id_from_retained_state_topic(msg.topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid state shadow topic: %s", msg.topic)
            return

        call_name = self._call_name_from_retained_state_topic(msg.topic)
        decoded_payload = self._decode_retained_state_payload(msg.payload)
        self.dgb_context.record_retained_state(
            unique_id=unique_id,
            call_name=call_name,
            args=decoded_payload,
        )

        with self._preload_lock:
            self._preload_last_activity = time.monotonic()

        self.logger.info(
            "Stored retained state value for %s from %s (%s: %s)",
            unique_id,
            msg.topic,
            call_name,
            decoded_payload,
        )

    # ------------------------------------------------------------------
    # phase 4.1: record retained state needs
    # ------------------------------------------------------------------

    def register_retained_state_need(self, raw_startup_policy: dict):
        # raw_atartup_policy has
        # "retain_state": [{"unique_id": "id", "call": ["call_name"]}]
        retain_devices = self.get_list(raw_startup_policy, "retain_state")
        for retain_device in retain_devices:
            call_names = self.get_list(retain_device, "call")
            self.dgb_context.record_retained_state_need(
                retain_device.get("unique_id"), call_names
            )

    def get_list(
        self,
        raw_startup_policy: dict[str, list],
        key: str,
    ) -> list:
        """Parse a bucket."""
        raw_list = raw_startup_policy.get(key, [])
        if isinstance(raw_list, dict):
            raw_list = [raw_list]
        if not isinstance(raw_list, list):
            raise TypeError(
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
            raise TypeError(
                f"Key {key} in given dict does not contain a dict, got {type(raw_list).__name__!r}"
            )
        return raw_list

    # ------------------------------------------------------------------
    # phase 4.2: record preset states
    # ------------------------------------------------------------------

    def register_preset_states(self, raw_sources: dict) -> None:
        """
        Parse preset state entries.
        raw_sources should contain "preset_value" that has a list with dicts with structure like:
        { "unique_id": "id", "call": "set_state", "args": [{"state_name": "Any"}]}

        For this DGB stage, preset startup values are restricted to:
        - call: "set_state"
        - args: [{"state_name": ...}, {"value": ...}]

        """
        raw_list = self.get_list(raw_sources, "preset_value")

        for raw in raw_list:
            if not isinstance(raw, dict):
                raise TypeError(
                    f"Key preset_value in given dict does not contain a dict, got {type(raw_list).__name__!r}"
                )
            unique_id = raw.get("unique_id")
            call_name = raw.get("call")
            args_list = self.get_list(raw, "args")
            if call_name != "set_state":
                raise ValueError("preset_value 'call' must be 'set_state' for now")

            self.dgb_context.record_preset_state(unique_id, call_name, args_list)

    # def _parse_state_args(self, args: dict[str, Any]) -> tuple[str, Any]:
    #     """Validate and normalize set_state startup args into (state_name, value)."""
    #     state_name_arg = args.get("name")
    #     value_arg = args.get("value")
    #     if not isinstance(state_name_arg, str):
    #         raise TypeError("preset_value arg 'name' must be str entries")
    #     if state_name_arg is None or value_arg is None:
    #         raise ValueError(
    #             "preset_value 'name' or 'value' are not or incorrect defined"
    #         )
    #     return state_name_arg, value_arg

    # ------------------------------------------------------------------
    # Phase 5: apply preset and retained states
    # ------------------------------------------------------------------

    def apply_startup_states(self) -> None:
        for dgb_object in self.dgb_context.DGB_objects.values():
            unique_id = dgb_object.unique_id
            # dict of preset states containing the {call_name: [args]}
            state_dict = dict(dgb_object.preset_state)
            self.logger.info(f"Found preset_states: {state_dict}")
            # check if retained state must be applied, if so override / add the {call_name: [args]}
            if dgb_object.retain_required and dgb_object.retained_state:
                for call_name, args in dgb_object.retained_state.items():
                    if call_name in dgb_object.retain_required:
                        state_dict[call_name] = args
                        self.logger.info(
                            f"Found retained_state: '{call_name}': {args} "
                        )
            if state_dict:
                # state_dict = self._map_startup_states(preset_state)
                self._apply_startup_state(unique_id=unique_id, state_dict=state_dict)

    # def _map_startup_states(
    #     self,
    #     state_values: dict[str, Any],
    # ) -> dict[str, Any]:
    #     args = []
    #     for state_name, value in state_values.items():
    #         args.append({"name": state_name, "value": value})
    #     state_dict = {
    #         "call": "set_state",
    #         "args": args,
    #     }
    #     return state_dict

    def _apply_startup_state(
        self,
        unique_id: str,
        state_dict: dict[str, list],
    ):
        if not isinstance(state_dict, dict):
            self.logger.warning(
                "Configured default for %s ignored: action payload must be a dict",
                unique_id,
            )
            return

        functions = self.dgb_context.get_functions(unique_id)
        if not functions:
            self.logger.warning(
                "Configured default for %s ignored: no registered functions",
                unique_id,
            )
            return

        for call_name, args in state_dict.items():
            function = functions.get(call_name)
            arg_def = self.arg_builder.parse_argument_definitions(args, function)
            call_args = self.arg_builder.build_call_args(arg_def, None)
            function(**call_args)
            self.logger.info(
                "Applied configured default via action call for %s (%s)",
                unique_id,
                call_name,
            )
        return True
