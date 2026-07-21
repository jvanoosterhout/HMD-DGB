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
#    Parser and model for the startup_policy config section.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

# loading_mode: controls how Creation -> Apply -> Live phases are orchestrated
LoadingMode = Literal["gated", "unsupervised"]

# unknown_state_policy: what to do when a unique_id has no resolved state source
UnknownStatePolicy = Literal["warn", "quarantine", "block"]

# ResolvedSource: the winning state initialization source for a unique_id
ResolvedSource = Literal["retain_state", "preset_value", "no_state"]

_VALID_LOADING_MODES: set[str] = {"gated", "unsupervised"}

_VALID_UNKNOWN_STATE_POLICIES: set[str] = {"warn", "quarantine", "block"}

_DEFAULT_LOADING_MODE: LoadingMode = "gated"
_DEFAULT_UNKNOWN_STATE_POLICY: UnknownStatePolicy = "warn"


@dataclass(frozen=True)
class StartupEntry:
    """A single entry in a state_initialization bucket."""

    unique_id: str
    value: Any = None


@dataclass(frozen=True)
class SourceDecision:
    """
    The resolved startup source decision for a single unique_id.

    source:         the primary intent (retain_state, preset_value, or no_state)
    value:          the configured value, only set when source == "preset_value"
    fallback:       used by Stage 5 when source == "retain_state" and the
                    retained topic has no value; defaults to "no_state"
    fallback_value: the configured value for the fallback, only set when
                    fallback == "preset_value"
    """

    unique_id: str
    source: ResolvedSource
    value: Any = None
    fallback: ResolvedSource = "no_state"
    fallback_value: Any = None


@dataclass(frozen=True)
class StateInitialization:
    """
    State initialization sources: what value each entity starts with.

    Precedence (highest first):
      retain_state > preset_value > no_state
    """

    retain_state: tuple[StartupEntry, ...]  # restore from retained MQTT shadow
    preset_value: tuple[StartupEntry, ...]  # apply a fixed startup value
    no_state: tuple[StartupEntry, ...]  # create/discover without forcing any value


@dataclass(frozen=True)
class StartupPolicy:
    """Normalized startup policy extracted from a config payload."""

    # Controls when phases progress and whether gating is enforced
    loading_mode: LoadingMode
    # Controls what value each entity starts with
    state_initialization: StateInitialization
    # Controls what to do when a unique_id has no resolved state source
    unknown_state_policy: UnknownStatePolicy


def _parse_entry(raw: Any, bucket_name: str) -> StartupEntry:
    """Parse a single entry dict into a StartupEntry."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"startup_policy.state_initialization.{bucket_name}: each entry must be a dict, got {type(raw).__name__!r}"
        )

    unique_id = raw.get("unique_id")
    if not isinstance(unique_id, str) or not unique_id.strip():
        raise ValueError(
            f"startup_policy.state_initialization.{bucket_name}: entry has missing or empty 'unique_id': {raw!r}"
        )

    return StartupEntry(unique_id=unique_id, value=raw.get("value", None))


def _parse_bucket(
    raw_sources: dict,
    key: str,
) -> tuple[StartupEntry, ...]:
    """Parse a bucket list from the raw state_initialization dict."""
    raw_list = raw_sources.get(key, [])
    if not isinstance(raw_list, list):
        raise ValueError(
            f"startup_policy.state_initialization.{key}: expected a list, got {type(raw_list).__name__!r}"
        )
    return tuple(_parse_entry(item, key) for item in raw_list)


def _parse_preset_value_bucket(raw_sources: dict) -> tuple[StartupEntry, ...]:
    """
    Parse preset_value entries.

    Supported shapes:
    - Action-like: {"unique_id": "id", "call": "fn", "args": [...]}
    - Single object for convenience instead of list.
    """
    raw_preset = raw_sources.get("preset_value", [])
    if isinstance(raw_preset, dict):
        raw_list = [raw_preset]
    elif isinstance(raw_preset, list):
        raw_list = raw_preset
    else:
        raise ValueError(
            "startup_policy.state_initialization.preset_value: expected a list or dict, "
            f"got {type(raw_preset).__name__!r}"
        )

    parsed: list[StartupEntry] = []
    for raw in raw_list:
        entry = _parse_entry(raw, "preset_value")

        call = raw.get("call")
        args = raw.get("args", [])
        if not isinstance(call, str) or not call:
            raise ValueError(
                "startup_policy.state_initialization.preset_value: 'call' must be non-empty str"
            )
        if not isinstance(args, list):
            raise ValueError(
                "startup_policy.state_initialization.preset_value: 'args' must be a list"
            )
        entry = StartupEntry(
            unique_id=entry.unique_id,
            value={"call": call, "args": args},
        )

        parsed.append(entry)

    return tuple(parsed)


def parse_startup_policy(raw_policy: dict[str, Any]) -> StartupPolicy:
    """
    Parse and normalize a raw startup_policy dict into a StartupPolicy.

    Fills in defaults for missing keys. Raises ValueError on invalid values.
    """
    if not isinstance(raw_policy, dict):
        raise ValueError(
            f"startup_policy must be a dict, got {type(raw_policy).__name__!r}"
        )

    # --- loading_mode ---
    raw_mode = raw_policy.get("loading_mode", _DEFAULT_LOADING_MODE)
    if raw_mode not in _VALID_LOADING_MODES:
        raise ValueError(
            f"startup_policy.loading_mode: unknown value {raw_mode!r}. "
            f"Valid values: {sorted(_VALID_LOADING_MODES)}"
        )
    loading_mode: LoadingMode = raw_mode  # type: ignore[assignment]

    # --- unknown_state_policy ---
    raw_usp = raw_policy.get("unknown_state_policy", _DEFAULT_UNKNOWN_STATE_POLICY)
    if raw_usp not in _VALID_UNKNOWN_STATE_POLICIES:
        raise ValueError(
            f"startup_policy.unknown_state_policy: unknown value {raw_usp!r}. "
            f"Valid values: {sorted(_VALID_UNKNOWN_STATE_POLICIES)}"
        )
    unknown_state_policy: UnknownStatePolicy = raw_usp  # type: ignore[assignment]

    # --- state_initialization ---
    raw_sources = raw_policy.get("state_initialization", {})
    if not isinstance(raw_sources, dict):
        raise ValueError(
            f"startup_policy.state_initialization: expected a dict, got {type(raw_sources).__name__!r}"
        )

    state_initialization = StateInitialization(
        retain_state=_parse_bucket(raw_sources, "retain_state"),
        preset_value=_parse_preset_value_bucket(raw_sources),
        no_state=_parse_bucket(raw_sources, "no_state"),
    )

    policy = StartupPolicy(
        loading_mode=loading_mode,
        state_initialization=state_initialization,
        unknown_state_policy=unknown_state_policy,
    )

    logger.info(
        "Parsed startup_policy: loading_mode=%s usp=%s retain=%d preset=%d no_state=%d",
        policy.loading_mode,
        policy.unknown_state_policy,
        len(policy.state_initialization.retain_state),
        len(policy.state_initialization.preset_value),
        len(policy.state_initialization.no_state),
    )

    return policy


def resolve_state_sources(
    state_initialization: StateInitialization,
) -> dict[str, SourceDecision]:
    """
    Resolve the winning startup source for each unique_id.

    Rules:
    - Items not listed in retain_state or preset_value default to no_state
      (absence from the returned dict means no_state).
    - preset_value produces a deterministic SourceDecision with source="preset_value".
    - retain_state is highest priority; if the same unique_id also appears in
      preset_value, the fallback is "preset_value"; otherwise "no_state".

    Returns:
        dict mapping unique_id -> SourceDecision for all items with a non-default
        source. Items absent from the result are implicitly no_state.
    """
    # Index preset_value entries for O(1) fallback lookup
    preset_index: dict[str, StartupEntry] = {
        e.unique_id: e for e in state_initialization.preset_value
    }

    decisions: dict[str, SourceDecision] = {}

    # preset_value entries (lowest explicit priority)
    for entry in state_initialization.preset_value:
        decisions[entry.unique_id] = SourceDecision(
            unique_id=entry.unique_id,
            source="preset_value",
            value=entry.value,
        )
        logger.info(
            "State source for '%s': preset_value (value=%r)",
            entry.unique_id,
            entry.value,
        )

    # retain_state entries override preset_value, carry fallback
    for entry in state_initialization.retain_state:
        preset = preset_index.get(entry.unique_id)
        if preset is not None:
            fallback: ResolvedSource = "preset_value"
            fallback_value = preset.value
            logger.info(
                "State source for '%s': retain_state (fallback=preset_value, fallback_value=%r)",
                entry.unique_id,
                fallback_value,
            )
            decisions[entry.unique_id] = SourceDecision(
                unique_id=entry.unique_id,
                source="retain_state",
                fallback=fallback,
                fallback_value=fallback_value,
            )
        else:
            logger.info(
                "State source for '%s': retain_state (fallback=no_state)",
                entry.unique_id,
            )
            decisions[entry.unique_id] = SourceDecision(
                unique_id=entry.unique_id,
                source="retain_state",
            )

    return decisions
