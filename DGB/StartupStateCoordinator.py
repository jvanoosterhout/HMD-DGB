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
#    Startup-state coordination and initialization for DGBservice.

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from DGB.DGBContext import DGBContext
from DGB.SetStateResolver import CallArgumentResolver


class StartupStateCoordinator:
    """Collect and apply retained and preset startup states for DGB objects."""

    def __init__(
        self,
        dgb_context: DGBContext,
        state_resolver: CallArgumentResolver,
        retained_calls_topic_prefix: str,
    ) -> None:
        """Initialize the startup-state coordinator.

        Args:
            dgb_context: Context that stores registered objects and startup state data.
            state_resolver: Resolver used to build callable arguments from startup state data.
            retained_calls_topic_prefix: Topic prefix used for retained call messages.
        """
        self.dgb_context = dgb_context
        self.logger = logging.getLogger("StartupStateCoordinator")
        self.state_resolver = state_resolver
        self.retained_calls_topic_prefix = retained_calls_topic_prefix.rstrip("/") + "/"

    # ------------------------------------------------------------------
    # StartupPhase.COLLECT: Preload retained calls from MQTT (helpers)
    # ------------------------------------------------------------------

    def is_retained_calls_topic(self, topic: str) -> bool:
        """Return whether a topic belongs to the retained state namespace."""
        return self._parse_retained_calls_topic(topic) is not None

    def _parse_retained_calls_topic(self, topic: str) -> tuple[str, str] | None:
        """Parse a retained state topic into its object ID and call name.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            A tuple containing the object unique ID and call name, or None for an invalid topic.
        """
        if not topic.startswith(self.retained_calls_topic_prefix):
            return None
        suffix = topic[len(self.retained_calls_topic_prefix) :].strip("/")
        if not suffix:
            return None
        unique_id, _, call_name = suffix.partition("/")
        if not unique_id:
            return None
        return unique_id, call_name or "set_state"

    def _unique_id_from_retained_calls_topic(self, topic: str) -> str | None:
        """Extract the object unique ID from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The object unique ID or None when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_calls_topic(topic)
        return parsed_topic[0] if parsed_topic else None

    def _call_name_from_retained_calls_topic(self, topic: str) -> str:
        """Extract the state call name from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The call name or an empty string when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_calls_topic(topic)
        return parsed_topic[1] if parsed_topic else ""

    # ------------------------------------------------------------------
    # StartupPhase.COLLECT: Preload retained calls from MQTT (message handling)
    # ------------------------------------------------------------------

    def handle_retained_call_message(self, payload: Any, topic: str) -> None:
        """Validate and store a retained state message in the DGB context.

        Args:
            msg: MQTT message containing the retained state topic and payload.
        """
        unique_id = self._unique_id_from_retained_calls_topic(topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid state shadow topic: %s", topic)
            return

        call_name = self._call_name_from_retained_calls_topic(topic)

        if call_name == "set_state":
            try:
                payload = self._validate_set_state_payload(payload)
            except (TypeError, ValueError) as exc:
                self.logger.warning(
                    "Ignoring retained set_state for %s on %s: %s",
                    unique_id,
                    topic,
                    exc,
                )
                return
        self.dgb_context.record_retained_call(
            unique_id=unique_id,
            call_name=call_name,
            args=payload,
        )

        self.logger.info(
            "Stored retained state value for %s from %s (%s: %s)",
            unique_id,
            topic,
            call_name,
            payload,
        )

    # ------------------------------------------------------------------
    # StartupPhase.DECLARE: Register persisted calls from config
    # ------------------------------------------------------------------

    def _validate_set_state_args(self, args_list: Any) -> list[dict[str, Any]]:
        """Validate named state values for set_state.

        Args:
            args_list: Candidate list containing name/value argument objects.

        Returns:
            A normalized list containing the validated state argument.
        """
        if not isinstance(args_list, list):
            args_list = [args_list]
        normalized = self.state_resolver.normalize_argument_definitions(args_list)
        if not normalized:
            raise ValueError("set_state args must contain at least one state")
        return normalized

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

    def declare_persisted_calls(self, raw_startup_policy: dict) -> None:
        """Register persisted call names from startup policy configuration.

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
            self.dgb_context.declare_persisted_calls(unique_id, call_names)

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
    # StartupPhase.DECLARE: Register preset calls from config
    # ------------------------------------------------------------------

    def register_preset_calls(self, raw_sources: dict) -> None:
        """Validate and register preset calls from startup configuration.

        Args:
            raw_sources: State initialization configuration containing preset_value key and entries. structured like:
             "unique_id": "id", "call": "set_state", "args": [{"name": "state", "value": "Any"}]}
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

            self.dgb_context.record_preset_call(
                unique_id, call_name, {"args": args_list}
            )

    # ------------------------------------------------------------------
    # StartupPhase.RESOLVE_AND_SEED: Merge and seed calls to objects
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_startup_states(
        preset_calls: dict[str, Any],
        retained_calls: dict[str, Any],
        persisted_calls: list[str],
    ) -> dict[str, Any]:
        """Merge retained calls over preset calls when they are persisted.

        Args:
            preset_calls: Configured default calls.
            retained_calls: Calls loaded from MQTT.
            persisted_calls: Call names configured to use retained values.

        Returns:
            A new state mapping with applicable retained values overriding presets.
        """
        merged_calls = dict(preset_calls)
        for call_name, args in retained_calls.items():
            if call_name in persisted_calls:
                merged_calls[call_name] = args
        return merged_calls

    def resolve_and_seed_startup_calls(self) -> None:
        """Merge preset and retained calls, then apply to every registered object."""
        for dgb_object in self.dgb_context.DGB_objects.values():
            unique_id = dgb_object.unique_id
            state_dict = self._merge_startup_states(
                dgb_object.preset_calls,
                dgb_object.retained_calls,
                dgb_object.persisted_calls,
            )
            if state_dict:
                self.logger.info(
                    "Found preset calls for unique_id %s: %s",
                    unique_id,
                    state_dict,
                )
            for call_name in set(state_dict) & set(dgb_object.persisted_calls):
                self.logger.info(
                    "Found retained call for unique_id %s (%s): %s",
                    unique_id,
                    call_name,
                    state_dict[call_name],
                )
            if state_dict:
                self._seed_call(unique_id=unique_id, state_dict=dict(state_dict))

    def _seed_call(
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

        functions = self.dgb_context.get_calls(unique_id)
        if not functions:
            self.logger.warning(
                "Configured default for %s ignored: no registered functions",
                unique_id,
            )
            return False

        for call_name, args in state_dict.items():
            if self._seed_single_call(
                unique_id, call_name, args, functions.get(call_name)
            ):
                return True
        return False

    def _seed_single_call(
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

        arg_defs = self.state_resolver.parse_argument_definitions(
            args.get("args"), function
        )
        call_args = self.state_resolver.build_call_args(arg_defs, None)
        function(**call_args)
        self.logger.info(
            "Applied configured default via action call for %s (%s)",
            unique_id,
            call_name,
        )
        return True
