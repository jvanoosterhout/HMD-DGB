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
#    Parser for startup_policy validation and startup-state payloads.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# DGB Startup Behavior Policy
# ------------------------------------------------------------------

# loading_mode: controls how Creation -> Apply -> Live phases are orchestrated
LoadingMode = Literal["gated", "unsupervised"]

# unknown_state_policy: what to do when a unique_id has no resolved state source
UnknownStatePolicy = Literal["warn", "quarantine", "block"]

_VALID_LOADING_MODES: set[str] = {"gated", "unsupervised"}

_VALID_UNKNOWN_STATE_POLICIES: set[str] = {"warn", "quarantine", "block"}

_DEFAULT_LOADING_MODE: LoadingMode = "gated"
_DEFAULT_UNKNOWN_STATE_POLICY: UnknownStatePolicy = "warn"


# ------------------------------------------------------------------
# DGB Startup Policy Model
# ------------------------------------------------------------------


@dataclass(frozen=True)
class StartupPolicy:
    """Normalized startup behavior policy for a config apply cycle."""

    # Controls when phases progress and whether gating is enforced
    loading_mode: LoadingMode
    # Controls what to do when a unique_id has no resolved state source
    unknown_state_policy: UnknownStatePolicy


# ------------------------------------------------------------------
# DGB Startup State Source Parsing
# ------------------------------------------------------------------

# def _parse_bucket(
#     raw_sources: dict,
#     key: str,
# ) -> tuple[str, ...]:
#     """Parse a unique_id bucket (used for retain_state registrations)."""
#     raw_list = raw_sources.get(key, [])
#     if not isinstance(raw_list, list):
#         raise ValueError(
#             f"startup_policy.state_initialization.{key}: expected a list, got {type(raw_list).__name__!r}"
#         )
#     return tuple(raw_sources.get("unique_id") for item in raw_list)


# def _parse_preset_value_bucket(raw_sources: dict) -> tuple[dict[str, Any], ...]:
#     """
#     Parse preset startup state entries.

#     For this DGB stage, preset startup values are restricted to:
#     - call: "set_state"
#     - args: [{"state_name": ...}, {"value": ...}]

#     Output is normalized to:
#     - {"unique_id": str, "state_name": str, "value": Any}
#     """
#     raw_preset = raw_sources.get("preset_value", [])
#     if isinstance(raw_preset, dict):
#         raw_list = [raw_preset]
#     elif isinstance(raw_preset, list):
#         raw_list = raw_preset
#     else:
#         raise TypeError(
#             "startup_policy.state_initialization.preset_value: expected a list or dict, "
#             f"got {type(raw_preset).__name__!r}"
#         )

#     parsed: list[dict[str, Any]] = []
#     for raw in raw_list:
#         unique_id = raw.get("unique_id")
#         state_name, value = _parse_set_state_args(raw)
#         parsed.append(
#             {
#                 "unique_id": unique_id,
#                 "state_name": state_name,
#                 "value": value,
#             }
#         )

#     return tuple(parsed)


# def _parse_set_state_args(raw_entry: dict[str, Any]) -> tuple[str, Any]:
#     """Validate and normalize set_state startup args into (state_name, value)."""
#     call = raw_entry.get("call")
#     args = raw_entry.get("args", [])
#     if call != "set_state":
#         raise ValueError(
#             "startup_policy.state_initialization.preset_value: 'call' must be 'set_state'"
#         )
#     if not isinstance(args, list) or len(args) != 2:
#         raise ValueError(
#             "startup_policy.state_initialization.preset_value: 'args' must contain state_name and value"
#         )

#     state_name_arg = args[0]
#     value_arg = args[1]
#     if not isinstance(state_name_arg, dict) or not isinstance(value_arg, dict):
#         raise TypeError(
#             "startup_policy.state_initialization.preset_value: args must be dict entries"
#         )
#     if len(state_name_arg) != 1 or "state_name" not in state_name_arg:
#         raise ValueError(
#             "startup_policy.state_initialization.preset_value: first arg must define state_name"
#         )
#     if len(value_arg) != 1 or "value" not in value_arg:
#         raise ValueError(
#             "startup_policy.state_initialization.preset_value: second arg must define value"
#         )

#     state_name = state_name_arg["state_name"]
#     if not isinstance(state_name, str) or not state_name.strip():
#         raise ValueError(
#             "startup_policy.state_initialization.preset_value: state_name must be non-empty str"
#         )
#     return state_name, value_arg["value"]


# ------------------------------------------------------------------
# DGB Policy Intake
# ------------------------------------------------------------------


# def parse_state_initialization(
#     raw_policy: dict[str, Any],
# ) -> tuple[tuple[str, ...], tuple[dict[str, Any], ...]]:
#     """Parse startup state sources used to seed DGBObject startup state."""
#     raw_sources = raw_policy.get("state_initialization", {})
#     if not isinstance(raw_sources, dict):
#         raise ValueError(
#             f"startup_policy.state_initialization: expected a dict, got {type(raw_sources).__name__!r}"
#         )

#     retain_state = "_parse_bucket(raw_sources, "retain_state")
#     preset_value = _parse_preset_value_bucket(raw_sources)
#     return retain_state, preset_value


def parse_startup_policy(raw_policy: dict[str, Any]) -> StartupPolicy:
    """
    Parse and normalize startup behavior controls for a config cycle.

    Startup state payloads are parsed separately via parse_state_initialization.
    This parser focuses on lifecycle behavior controls.
    """
    if not isinstance(raw_policy, dict):
        raise TypeError(
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

    # retain_state, preset_value = parse_state_initialization(raw_policy)

    policy = StartupPolicy(
        loading_mode=loading_mode,
        unknown_state_policy=unknown_state_policy,
    )

    logger.info(
        "Parsed startup_policy: loading_mode=%s usp=%s retain=%d preset=%d",
        policy.loading_mode,
        policy.unknown_state_policy,
        0,
        0,
    )

    return policy
