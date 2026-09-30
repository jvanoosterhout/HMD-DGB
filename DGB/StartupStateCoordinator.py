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
        retained_actions_topic_prefix: str,
    ) -> None:
        """Initialize the startup-state coordinator.

        Args:
            dgb_context: Context that stores registered objects and startup state data.
            state_resolver: Resolver used to build callable arguments from startup state data.
            retained_actions_topic_prefix: Topic prefix used for retained action messages.
        """
        self.dgb_context = dgb_context
        self.logger = logging.getLogger("StartupStateCoordinator")
        self.state_resolver = state_resolver
        self.retained_actions_topic_prefix = (
            retained_actions_topic_prefix.rstrip("/") + "/"
        )

    # ------------------------------------------------------------------
    # StartupPhase.COLLECT: Preload retained actions from MQTT (helpers)
    # ------------------------------------------------------------------

    def is_retained_actions_topic(self, topic: str) -> bool:
        """Return whether a topic belongs to the retained state namespace."""
        return self._parse_retained_actions_topic(topic) is not None

    def _parse_retained_actions_topic(self, topic: str) -> tuple[str, str] | None:
        """Parse a retained state topic into its object ID and operation/call name.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            A tuple containing the object unique ID and operation/call name, or None for an invalid topic.
        """
        if not topic.startswith(self.retained_actions_topic_prefix):
            return None
        suffix = topic[len(self.retained_actions_topic_prefix) :].strip("/")
        if not suffix:
            return None
        unique_id, _, operation_name = suffix.partition("/")
        if not unique_id:
            return None
        return unique_id, operation_name or "set_state"

    def _unique_id_from_retained_actions_topic(self, topic: str) -> str | None:
        """Extract the object unique ID from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The object unique ID or None when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_actions_topic(topic)
        return parsed_topic[0] if parsed_topic else None

    def _operation_name_from_retained_actions_topic(self, topic: str) -> str:
        """Extract the state operation/call name from a retained state topic.

        Args:
            topic: MQTT topic to inspect.

        Returns:
            The operation/call name or an empty string when the topic is outside the configured namespace.
        """
        parsed_topic = self._parse_retained_actions_topic(topic)
        return parsed_topic[1] if parsed_topic else ""

    # ------------------------------------------------------------------
    # StartupPhase.COLLECT: Preload retained actions from MQTT (message handling)
    # ------------------------------------------------------------------

    def handle_retained_action_message(self, payload: Any, topic: str) -> None:
        """Validate and store a retained action message in the DGB context.

        Args:
            msg: MQTT message containing the retained action topic and payload.
        """
        unique_id = self._unique_id_from_retained_actions_topic(topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid action shadow topic: %s", topic)
            return

        operation_name = self._operation_name_from_retained_actions_topic(topic)

        if operation_name == "set_state":
            try:
                payload = self._validate_set_state_payload(payload)
            except (TypeError, ValueError) as exc:
                self.logger.warning(
                    "Ignoring retained action for %s on %s: %s",
                    unique_id,
                    topic,
                    exc,
                )
                return
        self.dgb_context.record_retained_action(
            unique_id=unique_id,
            operation_name=operation_name,
            args=payload,
        )

        self.logger.info(
            "Stored retained action value for %s from %s (%s: %s)",
            unique_id,
            topic,
            operation_name,
            payload,
        )

    # ------------------------------------------------------------------
    # StartupPhase.DECLARE: Register persisted actions from config
    # ------------------------------------------------------------------

    def _validate_set_state_args(self, args_list: Any) -> list[dict[str, Any]]:
        """Validate named values for set_state.

        Args:
            args_list: Candidate list containing name/value argument objects.

        Returns:
            A normalized list containing the validated arguments.
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
            payload: Decoded retained action payload to validate.

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

    def declare_persisted_actions(self, raw_startup_policy: dict) -> None:
        """Register persisted actions from startup policy configuration.

        Args:
            raw_startup_policy: State initialization configuration containing persist_action entries.
        """
        retain_devices = self.get_list(raw_startup_policy, "persist_action")
        for retain_device in retain_devices:
            if not isinstance(retain_device, dict):
                raise TypeError("persist_action entries must be dictionaries")
            unique_id = retain_device.get("unique_id")
            if not isinstance(unique_id, str) or not unique_id.strip():
                raise ValueError("persist_action 'unique_id' must be a non-empty str")
            operation_names = self.get_list(retain_device, "call")
            if not operation_names or not all(
                isinstance(operation_name, str) and operation_name.strip()
                for operation_name in operation_names
            ):
                raise ValueError("persist_action 'call' must contain non-empty strings")
            self.dgb_context.declare_persisted_actions(unique_id, operation_names)

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
    # StartupPhase.DECLARE: Register preset actions from config
    # ------------------------------------------------------------------

    def register_preset_actions(self, raw_sources: dict) -> None:
        """Validate and register preset actions from startup configuration.

        Args:
            raw_sources: State initialization configuration containing preset_action key and entries. structured like:
             "unique_id": "id", "call": "set_state", "args": [{"name": "state", "value": "Any"}]}
        """
        raw_list = self.get_list(raw_sources, "preset_action")

        for raw in raw_list:
            if not isinstance(raw, dict):
                raise TypeError(
                    f"Key preset_action in given dict does not contain a dict, got {type(raw_list).__name__!r}"
                )
            unique_id = raw.get("unique_id")
            if not isinstance(unique_id, str) or not unique_id.strip():
                raise ValueError("preset_action 'unique_id' must be a non-empty str")
            operation_name = raw.get("call")
            args_list = self.get_list(raw, "args")
            if operation_name != "set_state":
                raise ValueError("preset_action 'call' must be 'set_state' for now")

            args_list = self._validate_set_state_args(args_list)

            self.dgb_context.record_preset_action(
                unique_id, operation_name, {"args": args_list}
            )

    # ------------------------------------------------------------------
    # StartupPhase.RESOLVE_AND_SEED: Merge and seed actions to objects
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_startup_states(
        preset_actions: dict[str, Any],
        retained_actions: dict[str, Any],
        persisted_actions: list[str],
    ) -> dict[str, Any]:
        """Merge retained actions over preset actions when they are persisted.

        Args:
            preset_actions: Configured default actions.
            retained_actions: Actions loaded from MQTT.
            persisted_actions: Operation names whose actions are persisted.

        Returns:
            A new action mapping with applicable retained actions overriding presets.
        """
        merged_actions = dict(preset_actions)
        for operation_name, args in retained_actions.items():
            if operation_name in persisted_actions:
                merged_actions[operation_name] = args
        return merged_actions

    def resolve_and_seed_startup_calls(self) -> None:
        """Merge preset and retained actions, then apply them to every registered object."""
        for dgb_object in self.dgb_context.DGB_objects.values():
            unique_id = dgb_object.unique_id
            state_dict = self._merge_startup_states(
                dgb_object.preset_actions,
                dgb_object.retained_actions,
                dgb_object.persisted_actions,
            )
            if state_dict:
                self.logger.info(
                    "Found preset actions for unique_id %s: %s",
                    unique_id,
                    state_dict,
                )
            for operation_name in set(state_dict) & set(dgb_object.persisted_actions):
                self.logger.info(
                    "Found retained action for unique_id %s (%s): %s",
                    unique_id,
                    operation_name,
                    state_dict[operation_name],
                )
            if state_dict:
                self._seed_call(unique_id=unique_id, state_dict=dict(state_dict))

    def _seed_call(
        self,
        unique_id: str,
        state_dict: dict[str, Any],
    ) -> bool:
        """Apply all configured actions for one object using the registered operation map.

        Args:
            unique_id: Unique ID of the object receiving the startup state.
            state_dict: Mapping of operation names to their argument payloads.

        Returns:
            True only when every startup action was applied successfully.
        """
        if not isinstance(state_dict, dict):
            self.logger.warning(
                "Configured default for %s ignored: action payload must be a dict",
                unique_id,
            )
            return False

        operations = self.dgb_context.get_operations(unique_id)
        if not operations:
            self.logger.warning(
                "Configured default for %s ignored: no registered operations",
                unique_id,
            )
            return False

        all_applied = True
        for operation_name, args in state_dict.items():
            if not self._seed_single_call(
                unique_id, operation_name, args, operations.get(operation_name)
            ):
                self.logger.warning(
                    "Seeding startup action %s for %s failed",
                    operation_name,
                    unique_id,
                )
                all_applied = False
        return all_applied

    def _seed_single_call(
        self,
        unique_id: str,
        operation_name: str,
        args: Any,
        function: Callable[..., Any] | None,
    ) -> bool:
        """Resolve and invoke one configured startup action.

        Args:
            unique_id: Unique ID of the object receiving the startup action.
            operation_name: Name of the operation to call.
            args: Argument payload for the operation.
            function: Registered callable for the operation.

        Returns:
            True when the operation was invoked and did not report failure.
        """
        if function is None:
            self.logger.warning(
                "Configured default for %s ignored: unknown operation %s",
                unique_id,
                operation_name,
            )
            return False
        if not isinstance(args, dict):
            self.logger.warning(
                "Configured default for %s ignored: arguments for %s must be a dict",
                unique_id,
                operation_name,
            )
            return False

        arg_defs = self.state_resolver.parse_argument_definitions(
            args.get("args"), function
        )
        call_args = self.state_resolver.build_call_args(arg_defs, None)
        result = function(**call_args)
        if result is False:
            return False
        self.logger.info(
            "Applied startup action for %s (%s)",
            unique_id,
            operation_name,
        )
        return True
