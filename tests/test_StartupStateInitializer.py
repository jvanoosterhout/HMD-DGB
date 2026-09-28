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
        retained_calls_topic_prefix="retained-calls/test/",
    )


def test_startup_topic_parsing_and_prefix_normalization(startup_initializer):
    """Retained state topics expose the expected object and call names."""
    assert startup_initializer.is_retained_calls_topic(
        "retained-calls/test/device/state"
    )
    assert not startup_initializer.is_retained_calls_topic(
        "retained-calls/testing/device/state"
    )
    assert (
        startup_initializer._unique_id_from_retained_calls_topic(
            "retained-calls/test/device/state"
        )
        == "device"
    )
    assert (
        startup_initializer._call_name_from_retained_calls_topic(
            "retained-calls/test/device/state"
        )
        == "state"
    )
    assert (
        startup_initializer._call_name_from_retained_calls_topic(
            "retained-calls/test/device"
        )
        == "set_state"
    )


def test_startup_topic_parsing_rejects_invalid_topics(startup_initializer):
    """Topics without an object ID or outside the namespace are rejected."""
    assert not startup_initializer.is_retained_calls_topic("retained-calls/test/")
    assert (
        startup_initializer._unique_id_from_retained_calls_topic("other/device") is None
    )
    assert (
        startup_initializer._call_name_from_retained_calls_topic("other/device") == ""
    )


def test_startup_payload_validation(startup_initializer):
    """Retained set_state payloads are normalized before storage."""
    payload = {"args": [{"name": "state", "value": "on"}]}
    assert startup_initializer._validate_set_state_payload(payload) == payload


def test_startup_message_stores_valid_state(startup_initializer):
    """A valid retained set_state message is recorded in the context."""
    payload = {"args": [{"name": "state", "value": "on"}]}
    startup_initializer.handle_retained_call_message(
        payload, "retained-calls/test/device/set_state"
    )
    startup_initializer.dgb_context.record_retained_call.assert_called_once_with(
        unique_id="device",
        call_name="set_state",
        args={"args": [{"name": "state", "value": "on"}]},
    )


def test_startup_message_stores_non_set_state_call(startup_initializer):
    """A valid non-set_state retained message is stored without set_state validation."""
    startup_initializer.handle_retained_call_message(
        "on", "retained-calls/test/device/turn_on"
    )
    startup_initializer.dgb_context.record_retained_call.assert_called_once_with(
        unique_id="device", call_name="turn_on", args="on"
    )


@pytest.mark.parametrize(
    ("payload", "topic"),
    [
        ("on", "other/device/state"),
        ("on", "retained-calls/test/device/set_state"),
        ({}, "retained-calls/test/device/set_state"),
    ],
)
def test_startup_message_ignores_invalid_state(payload, topic, startup_initializer):
    """Invalid retained state messages are ignored without recording state."""
    startup_initializer.handle_retained_call_message(payload, topic)
    startup_initializer.dgb_context.record_retained_call.assert_not_called()


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
    startup_initializer.declare_persisted_calls(
        {"retain_state": {"unique_id": "device", "call": ["set_state"]}}
    )
    startup_initializer.register_preset_calls(
        {
            "preset_value": {
                "unique_id": "device",
                "call": "set_state",
                "args": [{"name": "state", "value": "off"}],
            }
        }
    )
    startup_initializer.dgb_context.declare_persisted_calls.assert_called_once_with(
        "device", ["set_state"]
    )
    startup_initializer.dgb_context.record_preset_call.assert_called_once_with(
        "device", "set_state", {"args": [{"name": "state", "value": "off"}]}
    )


@pytest.mark.parametrize(
    "registration",
    [
        {"retain_state": ["invalid"]},
        {"retain_state": {"unique_id": "", "call": ["set_state"]}},
        {"retain_state": {"unique_id": "device", "call": [""]}},
        {"retain_state": {"unique_id": "device", "call": []}},
    ],
)
def test_startup_configuration_registration_rejects_invalid_values(
    registration, startup_initializer
):
    """Startup registration rejects malformed entries and call names."""
    with pytest.raises((TypeError, ValueError)):
        startup_initializer.declare_persisted_calls(registration)


def test_startup_preset_registration_rejects_invalid_entries(startup_initializer):
    """Preset registration rejects malformed entries and unsupported calls."""
    with pytest.raises(TypeError):
        startup_initializer.register_preset_calls({"preset_value": ["invalid"]})
    with pytest.raises(ValueError, match="unique_id"):
        startup_initializer.register_preset_calls(
            {"preset_value": {"call": "set_state", "args": []}}
        )
    with pytest.raises(ValueError, match="set_state"):
        startup_initializer.register_preset_calls(
            {
                "preset_value": {
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
    startup_initializer.dgb_context.get_calls.return_value = {"set_state": function}
    state = {"set_state": {"args": [{"name": "state", "value": "on"}]}}
    assert startup_initializer._seed_call("device", state) is True
    function.assert_called_once_with(state="on")


def test_startup_state_application_calls_multiple_named_states(startup_initializer):
    """One set_state call can apply multiple named state values."""
    function = MagicMock()
    startup_initializer.dgb_context.get_calls.return_value = {"set_state": function}
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
    startup_initializer.dgb_context.get_calls.return_value = {"set_state": MagicMock()}
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
    startup_initializer.dgb_context.get_calls.return_value = {}
    assert startup_initializer._seed_call("device", {"set_state": {}}) is False


def test_apply_startup_states_merges_and_applies_object_states(startup_initializer):
    """Startup state resolution merges object state and delegates seeding to helper."""
    dgb_object = SimpleNamespace(
        unique_id="device",
        preset_calls={"set_state": {"args": [{"name": "state", "value": "off"}]}},
        retained_calls={"set_state": {"args": [{"name": "state", "value": "on"}]}},
        persisted_calls=["set_state"],
    )
    startup_initializer.dgb_context.DGB_objects = {"device": dgb_object}
    with patch.object(startup_initializer, "_seed_call") as apply:
        startup_initializer.resolve_and_seed_startup_calls()
    apply.assert_called_once_with(
        unique_id="device",
        state_dict={"set_state": {"args": [{"name": "state", "value": "on"}]}},
    )
