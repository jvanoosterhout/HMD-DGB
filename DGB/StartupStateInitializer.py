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
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from DGB.DGBContext import DGBContext
from DGB.SetStateResolver import SetStateResolver


class StartupStateInitializer:
    """Collect and apply retained and preset startup states for DGB objects."""

    def __init__(
        self,
        dgb_context: DGBContext,
        mqtt_client: mqtt.Client,
        state_resolver: SetStateResolver,
        state_retain_topic_prefix: str,
        preload_quiet_seconds: float = 0.5,
        preload_timeout_seconds: float = 1.0,
    ) -> None:
        """Initialize the startup-state coordinator and its MQTT preload settings.

        Args:
            dgb_context: Context that stores registered objects and startup state data.
            mqtt_client: MQTT client used to subscribe to retained state topics.
            state_resolver: Resolver used to build callable arguments from startup state data.
            state_retain_topic_prefix: Topic prefix used for retained state messages.
            preload_quiet_seconds: Number of quiet seconds required before the preload window closes.
            preload_timeout_seconds: Maximum number of seconds allowed for the preload window.
        """
        self.dgb_context = dgb_context
        self.mqtt_client = mqtt_client
        self.logger = logging.getLogger("StartupStateInitializer")
        self.state_resolver = state_resolver
        self.retained_state_topic_prefix = state_retain_topic_prefix.rstrip("/") + "/"
        self.preload_quiet_seconds = preload_quiet_seconds
        self.preload_timeout_seconds = preload_timeout_seconds
        self._preload_lock = threading.Lock()
        self._preload_active = False
        self._preload_last_activity = time.monotonic()

    # ------------------------------------------------------------------
    # 1.1) Preload Values from MQTT: helpers
    # ------------------------------------------------------------------

    def is_state_shadow_topic(self, topic: str) -> bool:
        """Return whether a topic belongs to the retained state namespace."""
        return self._parse_retained_state_topic(topic) is not None

    def _parse_retained_state_topic(self, topic: str) -> tuple[str, str] | None:
        """Parse a retained state topic into its object ID and call name.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            A tuple containing the object unique ID and call name, or None for an invalid topic.
        """
        if not topic.startswith(self.retained_state_topic_prefix):
            return None
        suffix = topic[len(self.retained_state_topic_prefix) :].strip("/")
        if not suffix:
            return None
        unique_id, _, call_name = suffix.partition("/")
        if not unique_id:
            return None
        return unique_id, call_name or "set_state"

    def _unique_id_from_retained_state_topic(self, topic: str) -> str | None:
        """Extract the object unique ID from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The object unique ID or None when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_state_topic(topic)
        return parsed_topic[0] if parsed_topic else None

    def _call_name_from_retained_state_topic(self, topic: str) -> str:
        """Extract the state call name from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The call name or an empty string when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_state_topic(topic)
        return parsed_topic[1] if parsed_topic else ""

    def _decode_retained_state_payload(self, payload: bytes) -> Any:
        """Decode a retained state payload as JSON when possible and text otherwise.

        Args:
            payload: Raw MQTT payload bytes to decode.

        Returns:
            The decoded JSON value or the decoded text payload.
        """
        try:
            raw = payload.decode()
        except UnicodeDecodeError as exc:
            raise ValueError("retained state payload is not valid UTF-8") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # ------------------------------------------------------------------
    # 1.2)Preload Values from MQTT: message handling
    # ------------------------------------------------------------------

    def handle_subscription_to_retained_state_topic(self) -> None:
        """Subscribe to retained state topics until the preload window becomes quiet or expires."""
        wildcard_topic = f"{self.retained_state_topic_prefix}#"
        now = time.monotonic()
        with self._preload_lock:
            self._preload_active = True
            self._preload_last_activity = now

        try:
            self.mqtt_client.subscribe(wildcard_topic, qos=1)
            self.logger.info("Preloading retained state from %s", wildcard_topic)

            deadline = now + self.preload_timeout_seconds
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

    def handle_retained_state_message(self, msg: mqtt.MQTTMessage) -> None:
        """Validate and store a retained state message in the DGB context.

        Args:
            msg: MQTT message containing the retained state topic and payload.
        """
        unique_id = self._unique_id_from_retained_state_topic(msg.topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid state shadow topic: %s", msg.topic)
            return

        call_name = self._call_name_from_retained_state_topic(msg.topic)
        try:
            decoded_payload = self._decode_retained_state_payload(msg.payload)
        except ValueError as exc:
            self.logger.warning(
                "Ignoring retained state for %s on %s: %s",
                unique_id,
                msg.topic,
                exc,
            )
            return
        if call_name == "set_state":
            try:
                decoded_payload = self._validate_set_state_payload(decoded_payload)
            except (TypeError, ValueError) as exc:
                self.logger.warning(
                    "Ignoring retained set_state for %s on %s: %s",
                    unique_id,
                    msg.topic,
                    exc,
                )
                return
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

    @staticmethod
    def _validate_set_state_args(args_list: Any) -> list[dict[str, Any]]:
        """Validate and normalize the single state argument expected by set_state.

        Args:
            args_list: Candidate list containing one state name and value mapping.

        Returns:
            A normalized list containing the validated state argument.
        """
        if not isinstance(args_list, list):
            raise TypeError("set_state args must be a list")
        if len(args_list) != 1:
            raise ValueError("set_state args must contain exactly one dict")

        state_arg = args_list[0]
        if not isinstance(state_arg, dict):
            raise TypeError("set_state args[0] must be a dict")

        expected_keys = {"state_name", "state"}
        actual_keys = set(state_arg.keys())
        if actual_keys != expected_keys:
            raise ValueError(
                "set_state args[0] must have exactly keys {'state_name', 'state'}"
            )

        state_name = state_arg.get("state_name")
        if not isinstance(state_name, str) or not state_name.strip():
            raise ValueError("set_state args[0].state_name must be a non-empty str")

        return [{"state_name": state_name, "state": state_arg["state"]}]

    def _validate_set_state_payload(self, payload: Any) -> Any:
        """Validate a set_state payload in either wrapped or direct argument form.

        Args:
            payload: Decoded retained state payload to validate.

        Returns:
            A normalized set_state payload containing the validated argument list.
        """
        if isinstance(payload, dict):
            args_list = payload.get("args")
            if args_list is None:
                raise ValueError("set_state payload dict must contain 'args'")
            validated = self._validate_set_state_args(args_list)
            return {"args": validated}

        return self._validate_set_state_args(payload)

    def register_retained_state_need(self, raw_startup_policy: dict) -> None:
        """Register the retained state calls requested by startup policy configuration.

        Args:
            raw_startup_policy: State initialization configuration containing retain_state entries.
        """
        retain_devices = self.get_list(raw_startup_policy, "retain_state")
        for retain_device in retain_devices:
            if not isinstance(retain_device, dict):
                raise TypeError("retain_state entries must be dictionaries")
            unique_id = retain_device.get("unique_id")
            if not isinstance(unique_id, str) or not unique_id.strip():
                raise ValueError("retain_state 'unique_id' must be a non-empty str")
            call_names = self.get_list(retain_device, "call")
            if not call_names or not all(
                isinstance(call_name, str) and call_name.strip()
                for call_name in call_names
            ):
                raise ValueError("retain_state 'call' must contain non-empty strings")
            self.dgb_context.record_retained_state_need(unique_id, call_names)

    def get_list(
        self,
        raw_startup_policy: dict[str, list],
        key: str,
    ) -> list[Any]:
        """Return a configuration as a list, promoting one mapping to a single-item list.

        Args:
            raw_startup_policy: Configuration mapping containing the requested bucket.
            key: Configuration key whose value should be returned.

        Returns:
            The value as a list.
        """
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
    ) -> dict[str, Any]:
        """Return a configuration as a dict mapping.

        Args:
            raw_startup_policy: Configuration mapping containing the requested bucket.
            key: Configuration key whose mapping value should be returned.

        Returns:
            The value as a dict mapping.
        """
        raw_dict = raw_startup_policy.get(key, {})
        if not isinstance(raw_dict, dict):
            raise TypeError(
                f"Key {key} in given dict does not contain a dict, got {type(raw_dict).__name__!r}"
            )
        return raw_dict

    # ------------------------------------------------------------------
    # phase 4.2: record preset states
    # ------------------------------------------------------------------

    def register_preset_states(self, raw_sources: dict) -> None:
        """Validate and register preset set_state values from startup configuration.

        Args:
            raw_sources: State initialization configuration containing preset_value key and entries structured like:
             "unique_id": "id", "call": "set_state", "args": [{"state_name": "state", "state": "Any"}]}
        """
        raw_list = self.get_list(raw_sources, "preset_value")

        for raw in raw_list:
            if not isinstance(raw, dict):
                raise TypeError(
                    f"Key preset_value in given dict does not contain a dict, got {type(raw_list).__name__!r}"
                )
            unique_id = raw.get("unique_id")
            if not isinstance(unique_id, str) or not unique_id.strip():
                raise ValueError("preset_value 'unique_id' must be a non-empty str")
            call_name = raw.get("call")
            args_list = self.get_list(raw, "args")
            if call_name != "set_state":
                raise ValueError("preset_value 'call' must be 'set_state' for now")

            args_list = self._validate_set_state_args(args_list)

            self.dgb_context.record_preset_state(
                unique_id, call_name, {"args": args_list}
            )

    # ------------------------------------------------------------------
    # Phase 5: apply preset and retained states
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_startup_states(
        preset_state: dict[str, Any],
        retained_state: dict[str, Any],
        retain_required: list[str],
    ) -> dict[str, Any]:
        """Merge retained states over preset states when their calls are required.

        Args:
            preset_state: Configured default state calls.
            retained_state: State calls loaded from MQTT.
            retain_required: Call names configured to use retained values.

        Returns:
            A new state mapping with applicable retained values overriding presets.
        """
        merged_state = dict(preset_state)
        for call_name, args in retained_state.items():
            if call_name in retain_required:
                merged_state[call_name] = args
        return merged_state

    def apply_startup_states(self) -> None:
        """Apply preset states and matching retained states to every registered object."""
        for dgb_object in self.dgb_context.DGB_objects.values():
            unique_id = dgb_object.unique_id
            state_dict = self._merge_startup_states(
                dgb_object.preset_state,
                dgb_object.retained_state,
                dgb_object.retain_required,
            )
            if state_dict:
                self.logger.info(
                    "Found preset states for unique_id %s: %s",
                    unique_id,
                    state_dict,
                )
            for call_name in set(state_dict) & set(dgb_object.retain_required):
                self.logger.info(
                    "Found retained state for unique_id %s (%s): %s",
                    unique_id,
                    call_name,
                    state_dict[call_name],
                )
            if state_dict:
                self._apply_startup_state(
                    unique_id=unique_id, state_dict=dict(state_dict)
                )

    def _apply_startup_state(
        self,
        unique_id: str,
        state_dict: dict[str, Any],
    ) -> bool:
        """Apply configured calls for one object using the registered function map.

        Args:
            unique_id: Unique ID of the object receiving the startup state.
            state_dict: Mapping of call names to their argument payloads.

        Returns:
            True when at least one startup call was applied, otherwise False.
        """
        if not isinstance(state_dict, dict):
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

        for call_name, args in state_dict.items():
            if self._apply_startup_call(
                unique_id, call_name, args, functions.get(call_name)
            ):
                return True
        return False

    def _apply_startup_call(
        self,
        unique_id: str,
        call_name: str,
        args: Any,
        function: Callable[..., Any] | None,
    ) -> bool:
        """Resolve and invoke one configured startup call.

        Args:
            unique_id: Unique ID of the object receiving the startup call.
            call_name: Name of the configured call.
            args: Argument payload for the configured call.
            function: Registered callable for the configured call.

        Returns:
            True when the call was invoked, otherwise False when it was ignored.
        """
        if function is None:
            self.logger.warning(
                "Configured default for %s ignored: unknown function %s",
                unique_id,
                call_name,
            )
            return False
        if not isinstance(args, dict):
            self.logger.warning(
                "Configured default for %s ignored: arguments for %s must be a dict",
                unique_id,
                call_name,
            )
            return False

        arg_def = self.state_resolver.parse_argument_definitions(
            args.get("args"), function
        )
        call_args = self.state_resolver.build_call_args(arg_def, None)
        function(**call_args)
        self.logger.info(
            "Applied configured default via action call for %s (%s)",
            unique_id,
            call_name,
        )
        return True
