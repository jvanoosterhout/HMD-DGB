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
    cmd: BinderCmd
    payload: dict[str, Any]


@dataclass(frozen=True)
class ConfigMessage:
    cmd: ConfigCmd
    payload: dict[str, Any]


class DuplicatePolicy(Enum):
    SKIP = "skip"
    REPLACE = "replace"


FunctionMap = dict[str, Callable[..., Any]]

_UNSET = object()


@dataclass
class DGBObject:
    unique_id: str
    dgb_obj: Any | None = None
    obj_functions: FunctionMap = field(default_factory=dict)
    obj_type: type[Any] | None = None
    retain_required: list[str] = field(default_factory=list)
    retained_state: dict[str, list] = field(default_factory=dict)
    preset_state: dict[str, list] = field(default_factory=dict)


class DGBContext:
    """
    Shared runtime context for DGB, containing:
    - device and GPIO pin registries (objects + callable functions)
    - bindings between devices and rulesets
    - message queue for binder/engine interaction
    - (optional) engine lock used by the durable_rules engine
    """

    def __init__(self) -> None:
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
        """Explicitly close context resources and signal shutdown."""
        if self._closed:
            return
        self._closed = True
        self.put_to_binder_queue("shutdown", {})
        self.put_to_config_queue("shutdown", {})
        self._logger.info("DGBContext closed (shutdown enqueued).")

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # object handling
    # ------------------------------------------------------------------

    def add_object(
        self,
        unique_id: str,
        obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
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
        dgb_object = self.DGB_objects.get(unique_id)
        if dgb_object is None:
            dgb_object = DGBObject(unique_id=unique_id)
            self.DGB_objects[unique_id] = dgb_object
        return dgb_object

    def get_object(self, unique_id: str) -> Any:
        dgb_object = self.DGB_objects.get(unique_id)
        return dgb_object.dgb_obj if dgb_object is not None else None

    def remove_object(self, unique_id: str) -> None:
        self.DGB_objects.pop(unique_id, None)

    def get_functions(self, unique_id: str) -> FunctionMap:
        dgb_object = self.DGB_objects.get(unique_id)
        if dgb_object is None:
            return {}
        return dgb_object.obj_functions

    def record_preset_state(
        self,
        unique_id: str,
        call_name: str,
        args: list[dict[str, Any]],
    ) -> None:
        """Register preset state value for a unique_id in one place."""
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            dgb_object.preset_state[call_name] = args

    def get_preset_state(self, unique_id: str) -> Any:
        with self._phase_lock:
            dgb_object = self.DGB_objects.get(unique_id)
            if dgb_object is None:
                return {}
            return dict(dgb_object.preset_state)

    # phase 1 preload mqtt retained values
    def record_retained_state(
        self,
        unique_id: str,
        call_name: str,
        args: Any,
    ) -> None:
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            dgb_object.retained_state[call_name] = args

    def get_retained_state(self, unique_id: str) -> dict[str, Any]:
        with self._phase_lock:
            dgb_object = self.DGB_objects.get(unique_id)
            if dgb_object is None:
                return {}
            return dict(dgb_object.retained_state)

    # phase 2 load retain needs from config
    def record_retained_state_need(
        self,
        unique_id: str,
        states: list[str],
    ) -> None:
        """Register retain/preset intent for a unique_id in one place."""
        with self._phase_lock:
            dgb_object = self._ensure_dgb_object(unique_id)
            for state_name in states:
                dgb_object.retain_required.append(state_name)

    def is_retain_required(self, unique_id: str) -> bool:
        with self._phase_lock:
            dgb_object = self.DGB_objects.get(unique_id)
            return bool(dgb_object and dgb_object.retain_required)

    def has_retained_state(self, unique_id: str) -> bool:
        with self._phase_lock:
            dgb_object = self.DGB_objects.get(unique_id)
            return bool(dgb_object and dgb_object.retained_state)

    def publish_state_to_retain(
        self,
        unique_id: str,
        state_name: str,
        value: Any,
    ) -> None:
        with self._phase_lock:
            prefix = self._retained_state_prefix
            publish_fn = self._retained_state_publish_fn

        if not prefix or publish_fn is None:
            return

        topic = f"{prefix}{unique_id}/{state_name}"
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError):
            payload = str(value)

        try:
            publish_fn(topic, payload=payload, qos=1, retain=True)
        except Exception:
            self._logger.exception(
                "Failed to publish retained state for %s/%s",
                unique_id,
                state_name,
            )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_ruleset_name(ruleset_name: str) -> str:
        # strip suffix after '$'
        return ruleset_name.split("$", 1)[0]

    def configure_retained_state_publishing(
        self,
        prefix: str,
        publish_fn: Callable[..., Any] | None,
    ) -> None:
        with self._phase_lock:
            self._retained_state_prefix = prefix
            self._retained_state_publish_fn = publish_fn

    # ------------------------------------------------------------------
    # bindings
    # ------------------------------------------------------------------

    def add_binding(self, device_id: str, ruleset_name: str) -> None:
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
        # return a copy to prevent external mutation
        return set(self._bindings.get(device_id, set()))

    def put_to_binder_queue(self, cmd: BinderCmd, payload: dict[str, Any]) -> None:
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.binder_queue.put(BinderMessage(cmd=cmd, payload=payload))

    # ------------------------------------------------------------------
    # config cycle
    # ------------------------------------------------------------------

    def begin_config_apply_cycle(self) -> int:
        """Start a new config-apply cycle and move to creation phase."""
        with self._phase_lock:
            self._config_apply_cycle_id += 1
            self._runtime_phase = "creation"
            cycle_id = self._config_apply_cycle_id

        self._logger.info("Config cycle %s started", cycle_id)
        return cycle_id

    def set_runtime_phase(self, phase: RuntimePhase) -> None:
        with self._phase_lock:
            self._runtime_phase = phase
            cycle_id = self._config_apply_cycle_id
        self._logger.info("Runtime phase set to %s (cycle=%s)", phase, cycle_id)

    def get_runtime_phase(self) -> RuntimePhase:
        with self._phase_lock:
            return self._runtime_phase

    def get_config_apply_cycle_id(self) -> int:
        with self._phase_lock:
            return self._config_apply_cycle_id

    def is_live_dispatch_enabled(self) -> bool:
        return self.get_runtime_phase() == "live"

    def is_binding_dispatch_allowed(self, ruleset_name: str) -> bool:
        """Check if a binding (ruleset) is allowed to dispatch based on its cycle."""
        normalized = self._normalize_ruleset_name(ruleset_name)
        with self._phase_lock:
            binding_cycle = self._binding_cycle.get(normalized, 0)
            return binding_cycle <= self._last_live_cycle_id

    def complete_config_cycle(self, cycle_id: int) -> None:
        """Mark a config cycle as complete and allow its bindings to dispatch."""
        with self._phase_lock:
            if cycle_id > self._last_live_cycle_id:
                self._last_live_cycle_id = cycle_id
                self._logger.info("Config cycle %s completed and is now live", cycle_id)

    def put_to_config_queue(self, cmd: ConfigCmd, payload: dict[str, Any]) -> None:
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.config_queue.put(ConfigMessage(cmd=cmd, payload=payload))

    def record_payload_hash(self, payload_hash: str) -> None:
        """Record that a payload has been applied, for idempotency tracking."""
        with self._phase_lock:
            self._applied_payload_hashes.add(payload_hash)

    def payload_already_applied(self, payload_hash: str) -> bool:
        """Check if a payload has already been applied (idempotency guard)."""
        with self._phase_lock:
            return payload_hash in self._applied_payload_hashes

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        """Compute a deterministic hash of a payload for deduplication."""
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_json.encode()).hexdigest()

    # def get_startup_state_snapshot(
    #     self,
    # ) -> list[tuple[str, dict[str, Any], bool, dict[str, Any]]]:
    #     """Return startup-state metadata copied from context objects."""
    #     with self._phase_lock:
    #         return [
    #             (
    #                 unique_id,
    #                 dict(dgb_object.preset_value),
    #                 dgb_object.retain_required,
    #                 dict(dgb_object.retained_state),
    #             )
    #             for unique_id, dgb_object in self.DGB_objects.items()
    #         ]

    # def record_preset_state(
    #     self,
    #     unique_id: str,
    #     state_name: str,
    #     value: Any,
    # ) -> None:
    #     with self._phase_lock:
    #         dgb_object = self._ensure_dgb_object(unique_id)
    #         dgb_object.preset_value[state_name] = value

    # def iter_objects(self) -> list[tuple[str, Any]]:
    #     return [
    #         (unique_id, dgb_object.dgb_obj)
    #         for unique_id, dgb_object in self.DGB_objects.items()
    #         if dgb_object.dgb_obj is not None
    #     ]
