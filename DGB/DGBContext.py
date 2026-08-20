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

import hashlib
import json
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

BinderCmd = Literal["post", "ruleset", "shutdown"]
ConfigCmd = Literal["apply", "shutdown"]
RuntimePhase = Literal["creation", "apply", "live", "blocked", "quarantine"]


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
        # Runtime starts in live mode to preserve existing behavior until a
        # config-apply cycle explicitly transitions phases.
        self._runtime_phase: RuntimePhase = "live"
        self._config_apply_cycle_id = 0
        self._applied_payload_hashes: set[str] = set()
        # Track which cycle each binding was registered in, and last completed cycle
        self._binding_cycle: dict[str, int] = {}
        self._last_live_cycle_id = 0
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
        # Record which cycle this binding was registered in
        with self._phase_lock:
            self._binding_cycle[normalized] = self._config_apply_cycle_id
        self._logger.info(
            "Added binding for device %s to ruleset %s (cycle %s)",
            device_id,
            normalized,
            self._config_apply_cycle_id,
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

    # ------------------------------------------------------------------
    # config cycle
    # ------------------------------------------------------------------

    def begin_config_apply_cycle(self) -> int:
        """Start a config cycle and move the runtime to creation phase.

        Returns:
            The newly started configuration cycle identifier.
        """
        with self._phase_lock:
            self._config_apply_cycle_id += 1
            self._runtime_phase = "creation"
            cycle_id = self._config_apply_cycle_id

        self._logger.info("Config cycle %s started", cycle_id)
        return cycle_id

    def set_runtime_phase(self, phase: RuntimePhase) -> None:
        """Set the current runtime phase.

        Args:
            phase: Runtime phase to enter.
        """
        with self._phase_lock:
            self._runtime_phase = phase
            cycle_id = self._config_apply_cycle_id
        self._logger.info("Runtime phase set to %s (cycle=%s)", phase, cycle_id)

    def get_runtime_phase(self) -> RuntimePhase:
        """Return the current runtime phase.

        Returns:
            The active runtime phase.
        """
        with self._phase_lock:
            return self._runtime_phase

    def get_config_apply_cycle_id(self) -> int:
        """Return the current configuration cycle identifier.

        Returns:
            The current configuration cycle identifier.
        """
        with self._phase_lock:
            return self._config_apply_cycle_id

    def is_live_dispatch_enabled(self) -> bool:
        """Return whether live event dispatch is enabled.

        Returns:
            ``True`` when the runtime is in the live phase.
        """
        return self.get_runtime_phase() == "live"

    def is_binding_dispatch_allowed(self, ruleset_name: str) -> bool:
        """Return whether a ruleset's binding may dispatch in the live cycle.

        Args:
            ruleset_name: Ruleset name, optionally including an instance suffix.

        Returns:
            ``True`` when the binding's registration cycle is live.
        """
        normalized = self._normalize_ruleset_name(ruleset_name)
        with self._phase_lock:
            binding_cycle = self._binding_cycle.get(normalized, 0)
            return binding_cycle <= self._last_live_cycle_id

    def complete_config_cycle(self, cycle_id: int) -> None:
        """Mark a configuration cycle as live for binding dispatch.

        Args:
            cycle_id: Configuration cycle identifier to complete.
        """
        with self._phase_lock:
            if cycle_id > self._last_live_cycle_id:
                self._last_live_cycle_id = cycle_id
                self._logger.info("Config cycle %s completed and is now live", cycle_id)

    def put_to_config_queue(self, cmd: ConfigCmd, payload: dict[str, Any]) -> None:
        """Queue a configuration command unless the context is closed.

        Args:
            cmd: Configuration command to enqueue.
            payload: Command payload.
        """
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.config_queue.put(ConfigMessage(cmd=cmd, payload=payload))

    def record_payload_hash(self, payload_hash: str) -> None:
        """Record a payload hash for idempotency checks.

        Args:
            payload_hash: Hash of a configuration payload.
        """
        with self._phase_lock:
            self._applied_payload_hashes.add(payload_hash)

    def payload_already_applied(self, payload_hash: str) -> bool:
        """Return whether a payload hash has already been recorded.

        Args:
            payload_hash: Hash of a configuration payload.

        Returns:
            ``True`` when the hash was previously recorded.
        """
        with self._phase_lock:
            return payload_hash in self._applied_payload_hashes

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        """Return a deterministic SHA-256 hash for a payload.

        Args:
            payload: Configuration payload to hash.

        Returns:
            The hexadecimal SHA-256 digest.
        """
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_json.encode()).hexdigest()
