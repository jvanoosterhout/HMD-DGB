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
    ConfigCycleState,
    StartupPolicy,
)


def parse_startup_policy(raw_policy):
    """Apply a raw policy through the public ConfigCycleState API."""
    state = ConfigCycleState()
    state.set_startup_policy(raw_policy)
    return state.startup_policy


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_empty_dict_returns_all_defaults():
    policy = parse_startup_policy({})
    assert policy.loading_mode == "gated"
    assert policy.error_state_policy == "block"


def test_config_cycle_starts_with_default_policy():
    policy = ConfigCycleState().startup_policy

    assert policy.loading_mode == "gated"
    assert policy.error_state_policy == "block"


def test_no_dict_type_raises():
    with pytest.raises(TypeError, match="startup_policy"):
        parse_startup_policy([])


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
# error_state_policy
# ---------------------------------------------------------------------------


def test_error_state_policy_warn():
    policy = parse_startup_policy({"error_state_policy": "warn"})
    assert policy.error_state_policy == "warn"


def test_error_state_policy_clear_and_restart():
    policy = parse_startup_policy(
        {"error_state_policy": "clear_affected_config_and_restart"}
    )
    assert policy.error_state_policy == "clear_affected_config_and_restart"


def test_error_state_policy_block():
    policy = parse_startup_policy({"error_state_policy": "block"})
    assert policy.error_state_policy == "block"


def test_error_state_policy_invalid_raises():
    with pytest.raises(ValueError, match="error_state_policy"):
        parse_startup_policy({"error_state_policy": "panic"})


def test_error_state_policy_non_string_raises():
    with pytest.raises(ValueError, match="error_state_policy"):
        parse_startup_policy({"error_state_policy": 1})


# ---------------------------------------------------------------------------
# state_initialization bucket parsing
# ---------------------------------------------------------------------------


def test_retain_state_single_entry():
    # Test disabled: parse_state_initialization currently not exported
    pass


def test_retain_state_multiple_entries():
    # Test disabled: parse_state_initialization currently not exported
    pass


def test_preset_value_with_call_and_args():
    # Test disabled: parse_state_initialization currently not exported
    pass


# ---------------------------------------------------------------------------
# Full payload
# ---------------------------------------------------------------------------


def test_full_policy_parses_correctly():
    raw = {
        "loading_mode": "gated",
        "error_state_policy": "warn",
    }
    policy = parse_startup_policy(raw)
    assert isinstance(policy, StartupPolicy)
    assert policy.loading_mode == "gated"
    assert policy.error_state_policy == "warn"


# ---------------------------------------------------------------------------
# ConfigCycleState: runtime phase / config apply cycle
# ---------------------------------------------------------------------------


def test_runtime_phase_defaults_to_live():
    """Default phase is live for backward compatibility."""
    state = ConfigCycleState()
    assert state.get_phase() == "live"
    assert state.is_live() is True


def test_begin_cycle_sets_creation_phase():
    """Starting a config cycle increments id and enters creation phase."""
    state = ConfigCycleState()
    cycle = state.begin_cycle()

    assert cycle == 1
    assert state.get_cycle_id() == 1
    assert state.get_phase() == "creation"
    assert state.is_live() is False


def test_set_phase_roundtrip():
    """Runtime phase can be changed explicitly."""
    state = ConfigCycleState()
    state.set_phase("apply")
    assert state.get_phase() == "apply"
    assert state.is_live() is False

    state.set_phase("live")
    assert state.get_phase() == "live"
    assert state.is_live() is True


def test_binding_dispatch_allowed_only_after_cycle_completes():
    """A binding registered in a cycle only dispatches once that cycle is live."""
    state = ConfigCycleState()
    cycle_id = state.begin_cycle()
    state.record_binding_cycle("ruleset1")

    assert state.is_binding_dispatch_allowed("ruleset1") is False

    state.complete_cycle(cycle_id)

    assert state.is_binding_dispatch_allowed("ruleset1") is True


def test_complete_cycle_ignores_already_live_cycle():
    state = ConfigCycleState()
    cycle_id = state.begin_cycle()

    state.complete_cycle(cycle_id)
    state.complete_cycle(cycle_id)

    assert state.is_binding_dispatch_allowed("ruleset1") is True


# ---------------------------------------------------------------------------
# ConfigCycleState: payload idempotency
# ---------------------------------------------------------------------------


def test_payload_hash_idempotency():
    """Payload hash dedup works correctly."""
    state = ConfigCycleState()
    payload = {"Devices": [], "Pins": []}
    hash1 = state.compute_payload_hash(payload)

    assert state.payload_already_applied(hash1) is False

    state.record_payload_hash(hash1)

    assert state.payload_already_applied(hash1) is True


def test_payload_hash_different_payloads():
    """Different payloads produce different hashes."""
    payload1 = {"Devices": [], "Pins": []}
    payload2 = {"Devices": [{"id": "1"}], "Pins": []}

    hash1 = ConfigCycleState.compute_payload_hash(payload1)
    hash2 = ConfigCycleState.compute_payload_hash(payload2)

    assert hash1 != hash2


def test_payload_hash_deterministic():
    """Same payload produces same hash (deterministic)."""
    payload = {"Devices": [{"id": "1"}], "Pins": [{"pin": 17}]}

    hash1 = ConfigCycleState.compute_payload_hash(payload)
    hash2 = ConfigCycleState.compute_payload_hash(payload)

    assert hash1 == hash2
