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

import logging
import queue
import threading
import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, Set, Literal
from ha_mqtt_discoverable import Discoverable
from enum import Enum

BinderCmd = Literal["post", "ruleset", "shutdown"]
ConfigCmd = Literal["apply", "shutdown"]
RuntimePhase = Literal["creation", "apply", "live", "blocked", "quarantine"]


@dataclass(frozen=True)
class BinderMessage:
    cmd: BinderCmd
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ConfigMessage:
    cmd: ConfigCmd
    payload: Dict[str, Any]


class DuplicatePolicy(Enum):
    SKIP = "skip"
    REPLACE = "replace"


FunctionMap = Dict[str, Callable[..., Any]]


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

        self._devices_objects: Dict[str, Discoverable] = {}
        self._devices_functions: Dict[str, FunctionMap] = {}

        self._pins_objects: Dict[str, Any] = {}
        self._pins_functions: Dict[str, FunctionMap] = {}

        # Bindings should be unique: device_id -> set(ruleset_name)
        self._bindings: Dict[str, Set[str]] = {}

        self.device_registry: dict[str, str] = {}

        self.binder_queue: "queue.Queue[BinderMessage]" = queue.Queue()
        self.config_queue: "queue.Queue[ConfigMessage]" = queue.Queue()
        self.engine_lock: threading.Lock = threading.Lock()

        self._phase_lock = threading.Lock()
        # Runtime starts in live mode to preserve existing behavior until a
        # config-apply cycle explicitly transitions phases.
        self._runtime_phase: RuntimePhase = "live"
        self._config_apply_cycle_id = 0
        self._applied_payload_hashes: Set[str] = set()
        # Track which cycle each binding was registered in, and last completed cycle
        self._binding_cycle: Dict[str, int] = {}
        self._last_live_cycle_id = 0

        self._closed = False
        self._logger.info("DGBContext initialized.")

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

    def add_device(
        self,
        unique_id: str,
        device_obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self._devices_objects[unique_id] = device_obj
        self._devices_functions[unique_id] = functions if functions else {}
        self._logger.info(
            "Added device %s with functions %s",
            unique_id,
            sorted(self._devices_functions[unique_id].keys()),
        )

    def add_pin(
        self,
        unique_id: str,
        pin_obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self._pins_objects[unique_id] = pin_obj
        self._pins_functions[unique_id] = functions if functions else {}
        self._logger.info(
            "Added pin %s with functions %s",
            unique_id,
            sorted(self._pins_functions[unique_id].keys()),
        )

    @staticmethod
    def _normalize_ruleset_name(ruleset_name: str) -> str:
        # strip suffix after '$'
        return ruleset_name.split("$", 1)[0]

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

    def get_bindings(self, device_id: str) -> Set[str]:
        # return a copy to prevent external mutation
        return set(self._bindings.get(device_id, set()))

    def get_device(self, unique_id: str) -> Any:
        return self._devices_objects.get(unique_id)

    def get_pin(self, unique_id: str) -> Any:
        return self._pins_objects.get(unique_id)

    def get_functions(self, unique_id: str) -> FunctionMap:
        if unique_id in self._devices_functions:
            return self._devices_functions[unique_id]
        if unique_id in self._pins_functions:
            return self._pins_functions[unique_id]
        return {}

    def begin_config_apply_cycle(self) -> int:
        """Start a new config-apply cycle and move to creation phase."""
        with self._phase_lock:
            self._config_apply_cycle_id += 1
            self._runtime_phase = "creation"
            cycle_id = self._config_apply_cycle_id

        self._logger.info("Config apply cycle %s started", cycle_id)
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

    def put_to_config_queue(self, cmd: ConfigCmd, payload: Dict[str, Any]) -> None:
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
    def compute_payload_hash(payload: Dict[str, Any]) -> str:
        """Compute a deterministic hash of a payload for deduplication."""
        import json

        payload_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_json.encode()).hexdigest()

    def put_to_binder_queue(self, cmd: BinderCmd, payload: Dict[str, Any]) -> None:
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.binder_queue.put(BinderMessage(cmd=cmd, payload=payload))
