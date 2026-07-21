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

import pytest
from DGB.StartupPolicy import (
    SourceDecision,
    StartupEntry,
    StartupPolicy,
    StateInitialization,
    parse_startup_policy,
    resolve_state_sources,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_empty_dict_returns_all_defaults():
    policy = parse_startup_policy({})
    assert policy.loading_mode == "gated"
    assert policy.unknown_state_policy == "warn"
    assert policy.state_initialization.retain_state == ()
    assert policy.state_initialization.preset_value == ()
    assert policy.state_initialization.no_state == ()


def test_missing_startup_policy_key_defaults():
    """Callers pass payload.get('startup_policy', {}) so empty dict is the no-policy case."""
    policy = parse_startup_policy({})
    assert policy.loading_mode == "gated"
    assert policy.unknown_state_policy == "warn"


# ---------------------------------------------------------------------------
# loading_mode
# ---------------------------------------------------------------------------


def test_loading_mode_gated():
    policy = parse_startup_policy({"loading_mode": "gated"})
    assert policy.loading_mode == "gated"


def test_loading_mode_unsupervised():
    policy = parse_startup_policy({"loading_mode": "unsupervised"})
    assert policy.loading_mode == "unsupervised"


def test_loading_mode_unknown_raises():
    with pytest.raises(ValueError, match="loading_mode"):
        parse_startup_policy({"loading_mode": "invalid_mode"})


def test_loading_mode_old_alias_raises():
    with pytest.raises(ValueError, match="loading_mode"):
        parse_startup_policy({"loading_mode": "safe_call"})


# ---------------------------------------------------------------------------
# unknown_state_policy
# ---------------------------------------------------------------------------


def test_unknown_state_policy_warn():
    policy = parse_startup_policy({"unknown_state_policy": "warn"})
    assert policy.unknown_state_policy == "warn"


def test_unknown_state_policy_quarantine():
    policy = parse_startup_policy({"unknown_state_policy": "quarantine"})
    assert policy.unknown_state_policy == "quarantine"


def test_unknown_state_policy_block():
    policy = parse_startup_policy({"unknown_state_policy": "block"})
    assert policy.unknown_state_policy == "block"


def test_unknown_state_policy_invalid_raises():
    with pytest.raises(ValueError, match="unknown_state_policy"):
        parse_startup_policy({"unknown_state_policy": "panic"})


# ---------------------------------------------------------------------------
# state_initialization bucket parsing
# ---------------------------------------------------------------------------


def test_retain_state_single_entry():
    policy = parse_startup_policy(
        {"state_initialization": {"retain_state": [{"unique_id": "water_meter"}]}}
    )
    assert policy.state_initialization.retain_state == (
        StartupEntry(unique_id="water_meter"),
    )


def test_retain_state_multiple_entries():
    policy = parse_startup_policy(
        {
            "state_initialization": {
                "retain_state": [
                    {"unique_id": "meter_a"},
                    {"unique_id": "meter_b"},
                ]
            }
        }
    )
    assert len(policy.state_initialization.retain_state) == 2
    assert policy.state_initialization.retain_state[0].unique_id == "meter_a"
    assert policy.state_initialization.retain_state[1].unique_id == "meter_b"


def test_preset_value_with_call_and_args():
    policy = parse_startup_policy(
        {
            "state_initialization": {
                "preset_value": [
                    {
                        "unique_id": "switch_one",
                        "call": "set_state",
                        "args": [{"name": "value", "value": "on"}],
                    }
                ]
            }
        }
    )
    assert policy.state_initialization.preset_value == (
        StartupEntry(
            unique_id="switch_one",
            value={
                "call": "set_state",
                "args": [{"name": "value", "value": "on"}],
            },
        ),
    )


def test_preset_value_missing_call_raises():
    with pytest.raises(ValueError, match="'call' must be non-empty str"):
        parse_startup_policy(
            {
                "state_initialization": {
                    "preset_value": [{"unique_id": "switch_one", "value": "on"}]
                }
            }
        )


def test_preset_value_args_not_list_raises():
    with pytest.raises(ValueError, match="'args' must be a list"):
        parse_startup_policy(
            {
                "state_initialization": {
                    "preset_value": [
                        {
                            "unique_id": "switch_one",
                            "call": "set_state",
                            "args": "not-a-list",
                        }
                    ]
                }
            }
        )


def test_preset_value_accepts_single_dict_shape():
    policy = parse_startup_policy(
        {
            "state_initialization": {
                "preset_value": {
                    "unique_id": "p1",
                    "call": "on",
                    "args": [],
                }
            }
        }
    )
    assert len(policy.state_initialization.preset_value) == 1
    assert policy.state_initialization.preset_value[0].unique_id == "p1"


def test_no_state_single_entry():
    policy = parse_startup_policy(
        {"state_initialization": {"no_state": [{"unique_id": "sensor_water_level"}]}}
    )
    assert policy.state_initialization.no_state == (
        StartupEntry(unique_id="sensor_water_level"),
    )


def test_empty_state_initialization():
    policy = parse_startup_policy({"state_initialization": {}})
    assert policy.state_initialization.retain_state == ()
    assert policy.state_initialization.preset_value == ()
    assert policy.state_initialization.no_state == ()


def test_state_initialization_not_a_dict_raises():
    with pytest.raises(ValueError, match="state_initialization"):
        parse_startup_policy({"state_initialization": ["not", "a", "dict"]})


# ---------------------------------------------------------------------------
# Full payload
# ---------------------------------------------------------------------------


def test_full_policy_parses_correctly():
    raw = {
        "loading_mode": "gated",
        "state_initialization": {
            "retain_state": [{"unique_id": "water_meter"}],
            "preset_value": [
                {
                    "unique_id": "switch_one",
                    "call": "set_state",
                    "args": [{"name": "value", "value": "on"}],
                }
            ],
            "no_state": [{"unique_id": "sensor_water_level"}],
        },
        "unknown_state_policy": "warn",
    }
    policy = parse_startup_policy(raw)
    assert isinstance(policy, StartupPolicy)
    assert isinstance(policy.state_initialization, StateInitialization)
    assert policy.loading_mode == "gated"
    assert policy.state_initialization.retain_state[0].unique_id == "water_meter"
    assert policy.state_initialization.preset_value[0].value == {
        "call": "set_state",
        "args": [{"name": "value", "value": "on"}],
    }
    assert policy.state_initialization.no_state[0].unique_id == "sensor_water_level"
    assert policy.unknown_state_policy == "warn"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_non_dict_raises():
    with pytest.raises(ValueError, match="must be a dict"):
        parse_startup_policy("not a dict")  # type: ignore


def test_bucket_not_a_list_raises():
    with pytest.raises(ValueError, match="expected a list"):
        parse_startup_policy({"state_initialization": {"retain_state": "water_meter"}})


def test_bucket_entry_not_a_dict_raises():
    with pytest.raises(ValueError, match="must be a dict"):
        parse_startup_policy(
            {"state_initialization": {"retain_state": ["water_meter"]}}
        )


def test_bucket_entry_missing_unique_id_raises():
    with pytest.raises(ValueError, match="unique_id"):
        parse_startup_policy(
            {"state_initialization": {"retain_state": [{"name": "no_uid"}]}}
        )


def test_bucket_entry_empty_unique_id_raises():
    with pytest.raises(ValueError, match="unique_id"):
        parse_startup_policy(
            {"state_initialization": {"retain_state": [{"unique_id": ""}]}}
        )


def test_bucket_entry_whitespace_unique_id_raises():
    with pytest.raises(ValueError, match="unique_id"):
        parse_startup_policy(
            {"state_initialization": {"retain_state": [{"unique_id": "   "}]}}
        )


# ---------------------------------------------------------------------------
# Stage 3: resolve_state_sources
# ---------------------------------------------------------------------------


def _make_state_init(retain=(), preset=(), no_state=()):
    return StateInitialization(
        retain_state=tuple(StartupEntry(unique_id=uid) for uid in retain),
        preset_value=tuple(
            StartupEntry(unique_id=uid, value=val) for uid, val in preset
        ),
        no_state=tuple(StartupEntry(unique_id=uid) for uid in no_state),
    )


def test_resolve_empty_returns_empty():
    decisions = resolve_state_sources(_make_state_init())
    assert decisions == {}


def test_resolve_preset_value_only():
    si = _make_state_init(
        preset=[
            (
                "switch_one",
                {"call": "set_state", "args": [{"name": "value", "value": "on"}]},
            )
        ]
    )
    decisions = resolve_state_sources(si)
    assert decisions["switch_one"] == SourceDecision(
        unique_id="switch_one",
        source="preset_value",
        value={"call": "set_state", "args": [{"name": "value", "value": "on"}]},
    )


def test_resolve_preset_value_with_empty_args():
    si = _make_state_init(preset=[("switch_one", {"call": "off", "args": []})])
    decisions = resolve_state_sources(si)
    assert decisions["switch_one"].source == "preset_value"
    assert decisions["switch_one"].value == {"call": "off", "args": []}


def test_resolve_retain_state_only():
    si = _make_state_init(retain=["water_meter"])
    decisions = resolve_state_sources(si)
    d = decisions["water_meter"]
    assert d.source == "retain_state"
    assert d.fallback == "no_state"
    assert d.fallback_value is None


def test_resolve_retain_state_with_preset_fallback():
    si = StateInitialization(
        retain_state=(StartupEntry(unique_id="meter"),),
        preset_value=(
            StartupEntry(
                unique_id="meter",
                value={"call": "set_state", "args": [{"name": "value", "value": "42"}]},
            ),
        ),
        no_state=(),
    )
    decisions = resolve_state_sources(si)
    d = decisions["meter"]
    assert d.source == "retain_state"
    assert d.fallback == "preset_value"
    assert d.fallback_value == {
        "call": "set_state",
        "args": [{"name": "value", "value": "42"}],
    }


def test_resolve_no_state_only_absent_from_decisions():
    si = _make_state_init(no_state=["sensor_level"])
    decisions = resolve_state_sources(si)
    assert "sensor_level" not in decisions


def test_resolve_retain_wins_over_preset():
    si = StateInitialization(
        retain_state=(StartupEntry(unique_id="dev1"),),
        preset_value=(
            StartupEntry(unique_id="dev1", value={"call": "off", "args": []}),
        ),
        no_state=(),
    )
    decisions = resolve_state_sources(si)
    assert decisions["dev1"].source == "retain_state"


def test_resolve_multiple_independent_items():
    si = StateInitialization(
        retain_state=(StartupEntry(unique_id="meter"),),
        preset_value=(StartupEntry(unique_id="switch", value="on"),),
        no_state=(StartupEntry(unique_id="sensor"),),
    )
    decisions = resolve_state_sources(si)
    assert decisions["meter"].source == "retain_state"
    assert decisions["switch"].source == "preset_value"
    assert "sensor" not in decisions


def test_resolve_decisions_are_independent():
    si = _make_state_init(
        retain=["a", "b"],
        preset=[("c", "1"), ("d", "2")],
    )
    decisions = resolve_state_sources(si)
    assert len(decisions) == 4
    assert decisions["a"].source == "retain_state"
    assert decisions["b"].source == "retain_state"
    assert decisions["c"].source == "preset_value"
    assert decisions["d"].source == "preset_value"
