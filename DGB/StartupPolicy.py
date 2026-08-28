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
#    Parser for startup_policy validation, plus config-apply cycle lifecycle
#    tracking (runtime phase, binding liveness, payload idempotency).

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# DGB Startup Behavior Policy
# ------------------------------------------------------------------


class LoadingMode(str, Enum):
    """Defines how configuration lifecycle phases are orchestrated."""

    GATED = "gated"
    UNSUPERVISED = "unsupervised"


class RuntimePhase(str, Enum):
    """Defines a configuration cycle lifecycle phase."""

    CREATION = "creation"
    APPLY = "apply"
    LIVE = "live"
    ERROR = "error"


class ErrorStatePolicy(str, Enum):
    """Defines the action when a configuration fails to load in the configuration cycle lifecycle."""

    WARN = "warn"
    BLOCK = "block"
    CLEAR_AFFECTED_CONFIG_AND_RESTART = "clear_affected_config_and_restart"
    REMOVE_AFFECTED_DEVICE_AND_BINDING = "remove_affected_device_and_binding"


_DEFAULT_LOADING_MODE = LoadingMode.GATED
_DEFAULT_ERROR_STATE_POLICY = ErrorStatePolicy.BLOCK

# ------------------------------------------------------------------
# DGB Startup Policy Model
# ------------------------------------------------------------------


@dataclass(frozen=True)
class StartupPolicy:
    """Stores normalized startup behavior for a configuration cycle."""

    # Controls when phases progress and whether gating is enforced
    loading_mode: LoadingMode
    # Controls what to do when a unique_id has no resolved state source
    error_state_policy: ErrorStatePolicy


# ------------------------------------------------------------------
# DGB Config-Apply Cycle / Runtime Phase Tracking
# ------------------------------------------------------------------


class ConfigCycleState:
    """Tracks configuration lifecycle state, binding liveness, and payload idempotency."""

    def __init__(self) -> None:
        """Initializes the tracker in the live phase before cycle zero."""
        self.logger = logging.getLogger("ConfigCycleState")
        self._lock = threading.Lock()
        # Runtime starts in live mode to preserve existing behavior until a
        # config-apply cycle explicitly transitions phases.
        self._runtime_phase: RuntimePhase = RuntimePhase.LIVE
        self._cycle_id = 0
        self._last_live_cycle_id = 0
        self._binding_cycle: dict[str, int] = {}
        self._applied_payload_hashes: set[str] = set()
        self.startup_policy = StartupPolicy(
            loading_mode=_DEFAULT_LOADING_MODE,
            error_state_policy=_DEFAULT_ERROR_STATE_POLICY,
        )

    def begin_cycle(self) -> int:
        """Starts a configuration cycle and enters the creation phase.

        Returns:
            The new configuration cycle identifier.
        """
        with self._lock:
            self._cycle_id += 1
            self._runtime_phase = RuntimePhase.CREATION
            return self._cycle_id

    def set_phase(self, phase: RuntimePhase) -> None:
        """Sets the current runtime phase.

        Args:
            phase: The runtime phase to enter.
        """
        with self._lock:
            self._runtime_phase = phase

    def get_phase(self) -> RuntimePhase:
        """Returns the current runtime phase.

        Returns:
            The active runtime phase.
        """
        with self._lock:
            return self._runtime_phase

    def get_cycle_id(self) -> int:
        """Returns the current configuration cycle identifier.

        Returns:
            The active configuration cycle identifier.
        """
        with self._lock:
            return self._cycle_id

    def is_live(self) -> bool:
        """Returns whether the runtime is in the live phase.

        Returns:
            ``True`` when the runtime is in the live phase.
        """
        return self.get_phase() == RuntimePhase.LIVE

    def record_binding_cycle(self, normalized_ruleset_name: str) -> int:
        """Records the cycle in which a ruleset binding was registered.

        Args:
            normalized_ruleset_name: The ruleset name without an instance suffix.

        Returns:
            The configuration cycle identifier recorded for the binding.
        """
        with self._lock:
            self._binding_cycle[normalized_ruleset_name] = self._cycle_id
            return self._cycle_id

    def is_binding_dispatch_allowed(self, normalized_ruleset_name: str) -> bool:
        """Returns whether a binding was registered in a live cycle.

        Args:
            normalized_ruleset_name: The ruleset name without an instance suffix.

        Returns:
            ``True`` when the binding's registration cycle is live.
        """
        with self._lock:
            binding_cycle = self._binding_cycle.get(normalized_ruleset_name, 0)
            return binding_cycle <= self._last_live_cycle_id

    def complete_cycle(self, cycle_id: int) -> None:
        """Marks a configuration cycle as live for binding dispatch.

        Args:
            cycle_id: The configuration cycle identifier to complete.

        Returns:
            ``True`` when this call advanced the live cycle id.
        """
        with self._lock:
            self._last_live_cycle_id = max(self._last_live_cycle_id, cycle_id)

    def record_payload_hash(self, payload_hash: str) -> None:
        """Records a payload hash for idempotency checks.

        Args:
            payload_hash: The hash of a configuration payload.
        """
        with self._lock:
            self._applied_payload_hashes.add(payload_hash)

    def payload_already_applied(self, payload_hash: str) -> bool:
        """Returns whether a payload hash has already been recorded.

        Args:
            payload_hash: The hash of a configuration payload.

        Returns:
            ``True`` when the hash was previously recorded.
        """
        with self._lock:
            return payload_hash in self._applied_payload_hashes

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        """Returns a deterministic SHA-256 hash for a payload.

        Args:
            payload: The configuration payload to hash.

        Returns:
            The hexadecimal SHA-256 digest.
        """
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_json.encode()).hexdigest()

    def set_startup_policy(self, raw_policy: dict[str, Any]) -> None:
        """Parses and stores startup behavior controls for a configuration cycle.

        Args:
            raw_policy: The raw startup policy mapping from a configuration payload.
        """
        if not isinstance(raw_policy, dict):
            raise TypeError(
                f"startup_policy must be a dict, got {type(raw_policy).__name__!r}"
            )

        # --- loading_mode ---
        raw_mode = raw_policy.get("loading_mode", _DEFAULT_LOADING_MODE)
        try:
            loading_mode = LoadingMode(raw_mode)
        except ValueError as exc:
            raise ValueError(
                f"startup_policy.loading_mode: unknown value {raw_mode!r}. "
                f"Valid values: {[mode.value for mode in LoadingMode]}"
            ) from exc

        # --- error_state_policy ---
        raw_usp = raw_policy.get("error_state_policy", _DEFAULT_ERROR_STATE_POLICY)
        try:
            error_state_policy = ErrorStatePolicy(raw_usp)
        except ValueError as exc:
            raise ValueError(
                f"startup_policy.error_state_policy: unknown value {raw_usp!r}. "
                f"Valid values: {[policy.value for policy in ErrorStatePolicy]}"
            ) from exc

        self.startup_policy = StartupPolicy(
            loading_mode=loading_mode,
            error_state_policy=error_state_policy,
        )

        self.logger.info(
            "Parsed startup_policy: loading_mode=%s; error_state_policy=%s",
            self.startup_policy.loading_mode,
            self.startup_policy.error_state_policy,
        )
