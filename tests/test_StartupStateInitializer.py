from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from DGB.SetStateResolver import CallArgumentResolver
from DGB.StartupStateCoordinator import StartupStateCoordinator


@pytest.fixture
def startup_initializer():
    """Create an initializer with isolated context and MQTT dependencies."""
    return StartupStateCoordinator(
        dgb_context=MagicMock(),
        state_resolver=CallArgumentResolver(),
        retained_actions_topic_prefix="retained-actions/test/",
    )


def test_startup_topic_parsing_and_prefix_normalization(startup_initializer):
    """Retained state topics expose the expected object and call names."""
    assert startup_initializer.is_retained_actions_topic(
        "retained-actions/test/device/state"
    )
    assert not startup_initializer.is_retained_actions_topic(
        "retained-actions/testing/device/state"
    )
    assert (
        startup_initializer._unique_id_from_retained_actions_topic(
            "retained-actions/test/device/state"
        )
        == "device"
    )
    assert (
        startup_initializer._operation_name_from_retained_actions_topic(
            "retained-actions/test/device/state"
        )
        == "state"
    )
    assert (
        startup_initializer._operation_name_from_retained_actions_topic(
            "retained-actions/test/device"
        )
        == "set_state"
    )


def test_startup_topic_parsing_rejects_invalid_topics(startup_initializer):
    """Topics without an object ID or outside the namespace are rejected."""
    assert not startup_initializer.is_retained_actions_topic("retained-actions/test/")
    assert (
        startup_initializer._unique_id_from_retained_actions_topic("other/device")
        is None
    )
    assert (
        startup_initializer._operation_name_from_retained_actions_topic("other/device")
        == ""
    )


def test_startup_payload_validation(startup_initializer):
    """Retained set_state payloads are normalized before storage."""
    payload = {"args": [{"name": "state", "value": "on"}]}
    assert startup_initializer._validate_set_state_payload(payload) == payload


def test_startup_message_stores_valid_state(startup_initializer):
    """A valid retained set_state message is recorded in the context."""
    payload = {"args": [{"name": "state", "value": "on"}]}
    startup_initializer.handle_retained_action_message(
        payload, "retained-actions/test/device/set_state"
    )
    startup_initializer.dgb_context.record_retained_action.assert_called_once_with(
        unique_id="device",
        operation_name="set_state",
        args={"args": [{"name": "state", "value": "on"}]},
    )


def test_startup_message_stores_non_set_state_call(startup_initializer):
    """A valid non-set_state retained message is stored without set_state validation."""
    startup_initializer.handle_retained_action_message(
        "on", "retained-actions/test/device/turn_on"
    )
    startup_initializer.dgb_context.record_retained_action.assert_called_once_with(
        unique_id="device", operation_name="turn_on", args="on"
    )


@pytest.mark.parametrize(
    ("payload", "topic"),
    [
        ("on", "other/device/state"),
        ("on", "retained-actions/test/device/set_state"),
        ({}, "retained-actions/test/device/set_state"),
    ],
)
def test_startup_message_ignores_invalid_state(payload, topic, startup_initializer):
    """Invalid retained state messages are ignored without recording state."""
    startup_initializer.handle_retained_action_message(payload, topic)
    startup_initializer.dgb_context.record_retained_action.assert_not_called()


def test_startup_state_argument_validation(startup_initializer):
    """The set_state validator accepts and normalizes the supported shape."""
    args = [{"name": "state", "value": "on"}]
    assert startup_initializer._validate_set_state_args(args) == args
    assert startup_initializer._validate_set_state_payload({"args": args}) == {
        "args": args
    }
    assert startup_initializer._validate_set_state_payload(args) == args


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        [{}],
        [{"name": "", "value": "on"}],
    ],
)
def test_startup_state_argument_validation_rejects_invalid_shapes(
    args, startup_initializer
):
    """The set_state validator rejects malformed argument shapes."""
    with pytest.raises((TypeError, ValueError)):
        startup_initializer._validate_set_state_args(args)


def test_startup_configuration_bucket_helpers(startup_initializer):
    """Configuration helpers normalize list buckets and preserve mapping buckets."""
    assert startup_initializer.get_list({"items": {"id": "device"}}, "items") == [
        {"id": "device"}
    ]
    assert startup_initializer.get_dict(
        {"settings": {"enabled": True}}, "settings"
    ) == {"enabled": True}
    with pytest.raises(TypeError):
        startup_initializer.get_list({"items": "invalid"}, "items")
    with pytest.raises(TypeError):
        startup_initializer.get_dict({"settings": []}, "settings")


def test_startup_configuration_registration(startup_initializer):
    """Persisted calls and preset values are recorded in the context."""
    startup_initializer.declare_persisted_actions(
        {"persist_action": {"unique_id": "device", "call": ["set_state"]}}
    )
    startup_initializer.register_preset_actions(
        {
            "preset_action": {
                "unique_id": "device",
                "call": "set_state",
                "args": [{"name": "state", "value": "off"}],
            }
        }
    )
    startup_initializer.dgb_context.declare_persisted_actions.assert_called_once_with(
        "device", ["set_state"]
    )
    startup_initializer.dgb_context.record_preset_action.assert_called_once_with(
        "device", "set_state", {"args": [{"name": "state", "value": "off"}]}
    )


@pytest.mark.parametrize(
    "registration",
    [
        {"persist_action": ["invalid"]},
        {"persist_action": {"unique_id": "", "call": ["set_state"]}},
        {"persist_action": {"unique_id": "device", "call": [""]}},
        {"persist_action": {"unique_id": "device", "call": []}},
    ],
)
def test_startup_configuration_registration_rejects_invalid_values(
    registration, startup_initializer
):
    """Startup registration rejects malformed entries and call names."""
    with pytest.raises((TypeError, ValueError)):
        startup_initializer.declare_persisted_actions(registration)


def test_startup_preset_registration_rejects_invalid_entries(startup_initializer):
    """Preset registration rejects malformed entries and unsupported calls."""
    with pytest.raises(TypeError):
        startup_initializer.register_preset_actions({"preset_action": ["invalid"]})
    with pytest.raises(ValueError, match="unique_id"):
        startup_initializer.register_preset_actions(
            {"preset_action": {"call": "set_state", "args": []}}
        )
    with pytest.raises(ValueError, match="set_state"):
        startup_initializer.register_preset_actions(
            {
                "preset_action": {
                    "unique_id": "device",
                    "call": "turn_on",
                    "args": [],
                }
            }
        )


def test_startup_state_merge_prefers_required_retained_values():
    """Required retained state overrides the corresponding preset value only."""
    preset = {"set_state": {"args": [{"name": "state", "value": "off"}]}}
    retained = {
        "set_state": {"args": [{"name": "state", "value": "on"}]},
        "turn_on": {"args": []},
    }
    merged = StartupStateCoordinator._merge_startup_states(
        preset, retained, ["set_state"]
    )
    assert merged["set_state"] == retained["set_state"]
    assert "turn_on" not in merged
    assert preset["set_state"] != merged["set_state"]


def test_startup_state_application_calls_registered_function(startup_initializer):
    """A registered startup call is resolved and invoked with keyword arguments."""
    function = MagicMock()
    startup_initializer.dgb_context.get_operations.return_value = {
        "set_state": function
    }
    state = {"set_state": {"args": [{"name": "state", "value": "on"}]}}
    assert startup_initializer._seed_call("device", state) is True
    function.assert_called_once_with(state="on")


def test_startup_state_application_calls_multiple_named_states(startup_initializer):
    """One set_state call can apply multiple named state values."""
    function = MagicMock()
    startup_initializer.dgb_context.get_operations.return_value = {
        "set_state": function
    }
    state = {
        "set_state": {
            "args": [
                {"name": "scaled_total", "value": 4.2},
                {"name": "count_total", "value": 42},
            ]
        }
    }

    assert startup_initializer._seed_call("device", state) is True
    function.assert_called_once_with(scaled_total=4.2, count_total=42)


def test_startup_state_application_ignores_missing_function(startup_initializer):
    """An unknown startup call is ignored and reports false."""
    startup_initializer.dgb_context.get_operations.return_value = {
        "set_state": MagicMock()
    }
    assert (
        startup_initializer._seed_single_call("device", "missing", {"args": []}, None)
        is False
    )


def test_startup_state_application_ignores_non_dict_arguments(startup_initializer):
    """A startup call with a non-dictionary payload is ignored and reports false."""
    function = MagicMock()
    assert (
        startup_initializer._seed_single_call("device", "set_state", [], function)
        is False
    )
    function.assert_not_called()


def test_startup_state_application_ignores_missing_functions(startup_initializer):
    """State seeding is ignored when the object has no registered functions."""
    startup_initializer.dgb_context.get_operations.return_value = {}
    assert startup_initializer._seed_call("device", {"set_state": {}}) is False


def test_seed_call_applies_all_actions(startup_initializer):
    """Every startup action is applied, not only the first one."""
    set_state = MagicMock(return_value=True)
    blink = MagicMock(return_value=None)
    startup_initializer.dgb_context.get_operations.return_value = {
        "set_state": set_state,
        "blink": blink,
    }
    actions = {
        "set_state": {"args": [{"name": "state", "value": "on"}]},
        "blink": {"args": []},
    }

    assert startup_initializer._seed_call("device", actions) is True
    set_state.assert_called_once_with(state="on")
    blink.assert_called_once_with()


def test_seed_call_reports_failure_and_warns_but_applies_remaining(
    startup_initializer, caplog
):
    """A failed action makes seeding report False while other actions still run."""
    set_state = MagicMock(return_value=False)
    blink = MagicMock(return_value=True)
    startup_initializer.dgb_context.get_operations.return_value = {
        "set_state": set_state,
        "blink": blink,
    }
    actions = {
        "set_state": {"args": [{"name": "state", "value": "bogus"}]},
        "missing": {"args": []},
        "blink": {"args": []},
    }

    with caplog.at_level("WARNING"):
        assert startup_initializer._seed_call("device", actions) is False

    blink.assert_called_once_with()
    assert "Seeding startup action set_state for device failed" in caplog.text
    assert "Seeding startup action missing for device failed" in caplog.text
    assert "Seeding startup action blink" not in caplog.text


def test_apply_startup_states_merges_and_applies_object_states(startup_initializer):
    """Startup state resolution merges object state and delegates seeding to helper."""
    dgb_object = SimpleNamespace(
        unique_id="device",
        preset_actions={"set_state": {"args": [{"name": "state", "value": "off"}]}},
        retained_actions={"set_state": {"args": [{"name": "state", "value": "on"}]}},
        persisted_actions=["set_state"],
    )
    startup_initializer.dgb_context.DGB_objects = {"device": dgb_object}
    with patch.object(startup_initializer, "_seed_call") as apply:
        startup_initializer.resolve_and_seed_startup_calls()
    apply.assert_called_once_with(
        unique_id="device",
        state_dict={"set_state": {"args": [{"name": "state", "value": "on"}]}},
    )
