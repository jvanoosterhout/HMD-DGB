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
#

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from DGB.StartupPolicy import ConfigCycleState

BinderCmd = Literal["post", "ruleset", "shutdown"]
ConfigCmd = Literal["apply", "shutdown"]


@dataclass(frozen=True)
class BinderMessage:
    """Command and payload queued for the binder."""

    cmd: BinderCmd
    payload: dict[str, Any]


@dataclass(frozen=True)
class ConfigMessage:
    """Command and payload queued for configuration handling."""

    cmd: ConfigCmd
    payload: dict[str, Any]
    source_topic: str | None = None


class DuplicatePolicy(Enum):
    """Policy used when a duplicate registration is encountered."""

    SKIP = "skip"
    REPLACE = "replace"


FunctionMap = dict[str, Callable[..., Any]]

_UNSET = object()


@dataclass
class DGBObject:
    """Registered object and its runtime state metadata."""

    unique_id: str
    dgb_obj: Any | None = None
    obj_functions: FunctionMap = field(default_factory=dict)
    obj_type: type[Any] | None = None
    retain_required: list[str] = field(default_factory=list)
    retained_state: dict[str, list] = field(default_factory=dict)
    preset_state: dict[str, list] = field(default_factory=dict)


class DGBContext:
    """Shared registries, queues, bindings, and lifecycle state for DGB."""

    def __init__(self) -> None:
        """Initialize an empty context in the live runtime phase."""
        self._logger = logging.getLogger(f"{__name__}.DGBContext")

        # availability topic for node and service
        self.availability_topic_ns = ""
        # availability topic for dgb devices
        # self.availability_topic_d = ""

        self.DGB_objects: dict[str, DGBObject] = {}

        # Bindings should be unique: device_id -> set(ruleset_name)
        self._bindings: dict[str, set[str]] = {}

        self.device_registry: dict[str, str] = {}

        self.binder_queue: queue.Queue[BinderMessage] = queue.Queue()
        self.config_queue: queue.Queue[ConfigMessage] = queue.Queue()
        self.engine_lock: threading.Lock = threading.Lock()

        self._phase_lock = threading.Lock()
        self.config_cycle = ConfigCycleState()
        self._retained_state_prefix = ""
        self._retained_state_publish_fn: Callable[..., Any] | None = None

        self._closed = False
        self._logger.info("DGBContext initialized.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the context and enqueue shutdown commands."""
        if self._closed:
            return
        self._closed = True
        self.put_to_binder_queue("shutdown", {})
        self.put_to_config_queue("shutdown", {})
        self._logger.info("DGBContext closed (shutdown enqueued).")

    def __exit__(self, exc_type, exc, tb) -> None:
        """Close the context when leaving a context-manager block.

        Args:
            exc_type: Exception class, if the block raised an exception.
            exc: Exception instance, if the block raised an exception.
            tb: Traceback, if the block raised an exception.
        """
        self.close()

    # ------------------------------------------------------------------
    # Generic object handling
    # ------------------------------------------------------------------

    def add_object(
        self,
        unique_id: str,
        obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        """Register or replace an object and its callable functions.

        Args:
            unique_id: Identifier used to register the object.
            obj: Device or pin object to register.
            functions: Callable operations exposed by the object.
        """
        fn_map: FunctionMap = functions if functions else {}
        dgb_object = self.DGB_objects.get(unique_id)
        if dgb_object is None:
            dgb_object = DGBObject(unique_id=unique_id)
            self.DGB_objects[unique_id] = dgb_object

        dgb_object.dgb_obj = obj
        dgb_object.obj_functions = fn_map
        dgb_object.obj_type = type(obj)
        self._logger.info(
            "Added object %s with functions %s",
            unique_id,
            sorted(dgb_object.obj_functions.keys()),
        )

    def _ensure_dgb_object(self, unique_id: str) -> DGBObject:
        """Return an existing object or create one for the identifier.

        Args:
            unique_id: Identifier of the object.

        Returns:
            The existing or newly created object.
        """
        dgb_object = self.DGB_objects.get(unique_id)
        if dgb_object is None:
            dgb_object = DGBObject(unique_id=unique_id)
            self.DGB_objects[unique_id] = dgb_object
        return dgb_object

    def get_object(self, unique_id: str) -> DGBObject | None:
        """Return the registered object, if present.

        Args:
            unique_id: Identifier of the registered object.

        Returns:
            The object, or ``None`` when it is not registered.
        """
        return self.DGB_objects.get(unique_id)

    def remove_object(self, unique_id: str) -> None:
        """Remove a registered object and ignore unknown identifiers.

        Args:
            unique_id: Identifier of the object to remove.
        """
        self.DGB_objects.pop(unique_id, None)

    def get_functions(self, unique_id: str) -> FunctionMap:
        """Return a registered object's callable map or an empty map.

        Args:
            unique_id: Identifier of the registered object.

        Returns:
            The object's callable map, or an empty map when absent.
        """
        dgb_object = self.DGB_objects.get(unique_id)
        if dgb_object is None:
            return {}
        return dgb_object.obj_functions

    def record_preset_state(
        self,
        unique_id: str,
        call_name: str,
        args: dict[str, list],
    ) -> None:
        """Store a configured startup state for an object.

        Args:
            unique_id: Identifier of the target object.
            call_name: State-setting call name.
            args: Arguments for the state-setting call.
        """
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            dgb_object.preset_state[call_name] = args

    # ------------------------------------------------------------------
    # Phase 1 record preload mqtt retained values
    # ------------------------------------------------------------------

    def record_retained_state(
        self,
        unique_id: str,
        call_name: str,
        args: Any,
    ) -> None:
        """Store a state loaded from an MQTT retained message.

        Args:
            unique_id: Identifier of the target object.
            call_name: State-setting call name.
            args: Decoded arguments from the retained message.
        """
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            dgb_object.retained_state[call_name] = args

    # ------------------------------------------------------------------
    # Phase 2 record retain needs from config
    # ------------------------------------------------------------------

    def record_retained_state_need(
        self,
        unique_id: str,
        states: list[str],
    ) -> None:
        """Record which state calls require retained values.

        Args:
            unique_id: Identifier of the target object.
            states: State-setting call names requiring retained values.
        """
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            for state_name in states:
                dgb_object.retain_required.append(state_name)

    # ------------------------------------------------------------------
    # Phase 5 retain state on mqtt topic
    # ------------------------------------------------------------------

    def is_retain_required(self, unique_id: str) -> bool:
        """Return whether an object has retained-state requirements.

        Args:
            unique_id: Identifier of the object to inspect.

        Returns:
            ``True`` when at least one retained state is required.
        """
        with self._phase_lock:
            dgb_object = self.DGB_objects.get(unique_id)
            return bool(dgb_object and dgb_object.retain_required)

    def publish_state_to_retain(
        self, unique_id: str, call_name: str, args: dict[str, list]
    ) -> None:
        """Publish an object's state to its configured retained topic.

        Args:
            unique_id: Identifier of the target object.
            call_name: State-setting call name used in the topic.
            args: Arguments to serialize and publish.
        """
        with self._phase_lock:
            prefix = self._retained_state_prefix
            publish_fn = self._retained_state_publish_fn

        if not prefix or publish_fn is None:
            return

        topic = f"{prefix}{unique_id}/{call_name}"
        try:
            payload = json.dumps(args)
        except (TypeError, ValueError):
            payload = str(args)

        try:
            publish_fn(topic, payload=payload, qos=1, retain=True)
        except Exception:
            self._logger.exception(
                "Failed to publish retained state for %s/%s",
                unique_id,
                call_name,
            )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_ruleset_name(ruleset_name: str) -> str:
        """Remove the instance suffix from a ruleset name.

        Args:
            ruleset_name: Ruleset name, optionally followed by ``$`` and a suffix.

        Returns:
            The base ruleset name.
        """
        return ruleset_name.split("$", 1)[0]

    def configure_retained_state_publishing(
        self,
        prefix: str,
        publish_fn: Callable[..., Any] | None,
    ) -> None:
        """Configure the topic prefix and callback for retained publishing.

        Args:
            prefix: MQTT topic prefix for retained state messages.
            publish_fn: MQTT publish callback, or ``None`` to disable publishing.
        """
        with self._phase_lock:
            self._retained_state_prefix = prefix
            self._retained_state_publish_fn = publish_fn

    # ------------------------------------------------------------------
    # bindings
    # ------------------------------------------------------------------

    def add_binding(self, device_id: str, ruleset_name: str) -> None:
        """Add a normalized device-to-ruleset binding if it is new.

        Args:
            device_id: Identifier of the device to bind.
            ruleset_name: Ruleset name, optionally including an instance suffix.
        """
        normalized = self._normalize_ruleset_name(ruleset_name)
        rulesets = self._bindings.setdefault(device_id, set())

        if normalized in rulesets:
            self._logger.info(
                "Device %s already had binding to ruleset %s", device_id, normalized
            )
            return

        rulesets.add(normalized)
        cycle_id = self.config_cycle.record_binding_cycle(normalized)
        self._logger.info(
            "Added binding for device %s to ruleset %s (cycle %s)",
            device_id,
            normalized,
            cycle_id,
        )

    def get_bindings(self, device_id: str) -> set[str]:
        """Return a copy of the rulesets bound to a device.

        Args:
            device_id: Identifier of the device to inspect.

        Returns:
            A set of normalized ruleset names.
        """
        return set(self._bindings.get(device_id, set()))

    def put_to_binder_queue(self, cmd: BinderCmd, payload: dict[str, Any]) -> None:
        """Queue a binder command unless the context is closed.

        Args:
            cmd: Binder command to enqueue.
            payload: Command payload.
        """
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.binder_queue.put(BinderMessage(cmd=cmd, payload=payload))

    def put_to_config_queue(
        self,
        cmd: ConfigCmd,
        payload: dict[str, Any],
        source_topic: str | None = None,
    ) -> None:
        """Queue a configuration command unless the context is closed.

        Args:
            cmd: Configuration command to enqueue.
            payload: Command payload.
            source_topic: MQTT topic from which the configuration was received.
        """
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.config_queue.put(
            ConfigMessage(cmd=cmd, payload=payload, source_topic=source_topic)
        )
