import queue
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from DGB.DeviceKeeper import DeviceKeeper, build_callback
from DGB.DGBContext import BinderMessage, ConfigMessage, DGBContext
from DGB.SetStateResolver import CallArgumentResolver

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dgb_context():
    """Create a fresh DGBContext for each test"""
    return DGBContext()


# ---------------------------------------------------------------------------
# Level 1: Device Management
# ---------------------------------------------------------------------------


def test_add_device_without_functions(dgb_context):
    """Test adding a device without functions"""
    device_obj = {"type": "relay"}
    dgb_context.add_object("relay1", device_obj)

    assert dgb_context.get_object("relay1").dgb_obj == device_obj
    assert dgb_context.get_operations("relay1") == {}


def test_add_device_with_functions(dgb_context):
    """Test adding a device with functions"""
    device_obj = {"type": "relay"}
    functions = {"on": lambda: True, "off": lambda: False}
    dgb_context.add_object("relay1", device_obj, operations=functions)

    assert dgb_context.get_object("relay1").dgb_obj == device_obj
    assert dgb_context.get_operations("relay1") == functions


@pytest.mark.parametrize(
    ("setter_name", "value", "device_action", "expected"),
    [
        ("_set_cover_state", "OPEN", "open", None),
        ("_set_valve_state", "OPEN", "open", None),
        ("_set_valve_state", 42, "position", 42),
        ("_set_switch_state", "ON", "on", None),
        ("_set_text_state", "hello", "set_text", "hello"),
        ("_set_number_state", 3.5, "set_value", 3.5),
        ("_set_select_state", "choice", "select_option", "choice"),
        ("_set_sensor_state", "reading", "set_state", "reading"),
        ("_set_binary_sensor_state", "on", "on", None),
    ],
)
def test_hmd_set_state_accepts_configured_state_argument(
    dgb_context, setter_name, value, device_action, expected
):
    keeper = DeviceKeeper(None, dgb_context)
    device = MagicMock()
    device._entity.unique_id = "entity1"
    device._entity.payload_on = "ON"
    device._entity.payload_off = "OFF"
    device._entity.payload_open = "OPEN"
    device._entity.payload_close = "CLOSE"
    device._entity.payload_stop = "STOP"
    operation = partial(getattr(keeper, setter_name), device)
    resolver = CallArgumentResolver()
    definitions = resolver.parse_argument_definitions(
        [{"name": "state", "value": value}], operation
    )

    assert operation(**resolver.build_call_args(definitions, None)) is True

    action = getattr(device, device_action)
    if expected is None:
        action.assert_called_once_with()
    else:
        action.assert_called_once_with(expected)


def test_switch_callback_suppresses_direct_transition(dgb_context):
    keeper = DeviceKeeper(None, dgb_context)
    device = MagicMock()
    device._entity.unique_id = "switch1"
    device._entity.payload_on = "ON"
    device._entity.payload_off = "OFF"
    operation = partial(keeper._set_switch_state, device)
    dgb_context.add_object("switch1", device, operations={"set_state": operation})
    entity = SimpleNamespace(component="switch", unique_id="switch1")
    message = SimpleNamespace(payload=b"ON")

    build_callback(entity, dgb_context, False)(None, None, message)
    device.on.assert_not_called()

    operation(state="ON")
    device.on.assert_called_once_with()


def test_valve_position_action_uses_named_position_and_persists_it(dgb_context):
    keeper = DeviceKeeper(None, dgb_context)
    device = MagicMock()
    device._entity.unique_id = "valve1"
    operation = partial(keeper._set_valve_state, device)
    resolver = CallArgumentResolver()
    definitions = resolver.parse_argument_definitions(
        [{"name": "position", "value": 42}], operation
    )

    with patch.object(keeper, "_persist_action_if_required") as persist:
        assert operation(**resolver.build_call_args(definitions, None)) is True

    device.position.assert_called_once_with(42)
    persist.assert_called_once_with(
        "valve1", {"args": [{"name": "position", "value": 42}]}
    )


def test_valve_mqtt_position_respects_direct_transition(dgb_context):
    keeper = DeviceKeeper(None, dgb_context)
    device = MagicMock()
    device._entity.unique_id = "valve1"
    dgb_context.add_object(
        "valve1",
        device,
        operations={"set_state": partial(keeper._set_valve_state, device)},
    )
    entity = SimpleNamespace(component="valve", unique_id="valve1")

    with patch.object(keeper, "_persist_action_if_required") as persist:
        build_callback(entity, dgb_context, False)(
            None, None, SimpleNamespace(payload=b"42")
        )

    device.position.assert_not_called()
    persist.assert_called_once_with(
        "valve1", {"args": [{"name": "position", "value": 42}]}
    )


def test_get_nonexistent_device(dgb_context):
    """Test getting a non-existent device returns None"""
    assert dgb_context.get_object("nonexistent") is None


# ---------------------------------------------------------------------------
# Level 1: Pin Management
# ---------------------------------------------------------------------------


def test_add_pin_without_functions(dgb_context):
    """Test adding a pin without functions"""
    pin_obj = {"pin": 17, "mode": "OUT"}
    dgb_context.add_object("gpio17", pin_obj)

    assert dgb_context.get_object("gpio17").dgb_obj == pin_obj
    assert dgb_context.get_operations("gpio17") == {}


def test_add_pin_with_functions(dgb_context):
    """Test adding a pin with functions"""
    pin_obj = {"pin": 17, "mode": "OUT"}
    functions = {"set_high": lambda: None, "set_low": lambda: None}
    dgb_context.add_object("gpio17", pin_obj, operations=functions)

    assert dgb_context.get_object("gpio17").dgb_obj == pin_obj
    assert dgb_context.get_operations("gpio17") == functions


def test_get_nonexistent_pin(dgb_context):
    """Test getting a non-existent pin returns None"""
    assert dgb_context.get_object("nonexistent") is None


def test_remove_object(dgb_context):
    """Removing an object makes it unavailable."""
    dgb_context.add_object("relay1", {"type": "relay"})

    dgb_context.remove_object("relay1")

    assert dgb_context.get_object("relay1") is None


def test_remove_unknown_object_is_ignored(dgb_context):
    """Removing an unknown object does not raise an error."""
    dgb_context.remove_object("unknown")


# ---------------------------------------------------------------------------
# Level 1: Binding Management
# ---------------------------------------------------------------------------


def test_add_binding(dgb_context):
    """Test adding a binding between device and ruleset"""
    dgb_context.add_binding("dev1", "ruleset1")

    bindings = dgb_context.get_bindings("dev1")
    assert "ruleset1" in bindings


def test_add_binding_normalizes_ruleset_name(dgb_context):
    """Test that binding names are normalized (stripped after $)"""
    dgb_context.add_binding("dev1", "ruleset1$extra")

    bindings = dgb_context.get_bindings("dev1")
    assert "ruleset1" in bindings
    assert "ruleset1$extra" not in bindings


def test_add_multiple_bindings_same_device(dgb_context):
    """Test adding multiple bindings to the same device"""
    dgb_context.add_binding("dev1", "ruleset1")
    dgb_context.add_binding("dev1", "ruleset2")

    bindings = dgb_context.get_bindings("dev1")
    assert "ruleset1" in bindings
    assert "ruleset2" in bindings


def test_add_duplicate_binding_ignored(dgb_context):
    """Test that adding the same binding twice is idempotent"""
    dgb_context.add_binding("dev1", "ruleset1")
    dgb_context.add_binding("dev1", "ruleset1")

    bindings = dgb_context.get_bindings("dev1")
    assert len(bindings) == 1
    assert "ruleset1" in bindings


def test_get_nonexistent_bindings(dgb_context):
    """Test getting bindings for non-existent device returns empty set"""
    bindings = dgb_context.get_bindings("nonexistent")
    assert bindings == set()


def test_get_bindings_returns_copy(dgb_context):
    """Test that get_bindings returns a copy to prevent external mutation"""
    dgb_context.add_binding("dev1", "ruleset1")
    bindings = dgb_context.get_bindings("dev1")
    bindings.add("ruleset2")

    # Original should not be modified
    assert dgb_context.get_bindings("dev1") == {"ruleset1"}


# ---------------------------------------------------------------------------
# Level 1: Get Functions - Mixed Sources
# ---------------------------------------------------------------------------


def test_get_calls_from_device(dgb_context):
    """Test getting operations from a device"""
    functions = {"on": lambda: True}
    dgb_context.add_object("dev1", {}, operations=functions)

    assert dgb_context.get_operations("dev1") == functions


def test_get_calls_from_pin(dgb_context):
    """Test getting operations from a pin"""
    functions = {"set": lambda: True}
    dgb_context.add_object("pin1", {}, operations=functions)

    assert dgb_context.get_operations("pin1") == functions


def test_get_calls_last_write_wins(dgb_context):
    """Unified object model: latest registration for a unique_id wins."""
    dev_functions = {"on": lambda: "device"}
    pin_functions = {"on": lambda: "pin"}
    dgb_context.add_object("id1", {}, operations=dev_functions)
    dgb_context.add_object("id1", {}, operations=pin_functions)

    assert dgb_context.get_operations("id1") == pin_functions


def test_get_calls_nonexistent(dgb_context):
    """Test getting operations for non-existent device/pin returns empty dict"""
    assert dgb_context.get_operations("nonexistent") == {}


def test_retained_value_updates_dgb_object_state_store(dgb_context):
    dgb_context.record_retained_action("switch_2", "state", "on")

    retained = dgb_context.get_object("switch_2").retained_actions
    assert retained == {"state": "on"}
    assert dgb_context.get_object("switch_2").retained_actions == {"state": "on"}


def test_record_preset_call_creates_and_updates_object(dgb_context):
    """Preset operations are stored on the object wrapper."""
    args = {"state": ["on"]}

    dgb_context.record_preset_action("switch_1", "set_state", args)

    assert dgb_context.get_object("switch_1").preset_actions == {"set_state": args}


def test_declare_persisted_calls_and_requirement(dgb_context):
    """Declaring persisted operations marks the object as required."""
    dgb_context.declare_persisted_actions("switch_1", ["set_state"])

    assert dgb_context.is_action_persisted("switch_1") is True
    assert dgb_context.get_object("switch_1").persisted_actions == ["set_state"]


def test_is_call_persisted_for_missing_or_unconfigured_object(dgb_context):
    """Objects without persisted-operation requirements return false."""
    dgb_context.add_object("switch_1", {})

    assert dgb_context.is_action_persisted("switch_1") is False
    assert dgb_context.is_action_persisted("unknown") is False


def test_publish_state_value_calls_publish_fn(dgb_context):
    publish_fn = MagicMock()
    dgb_context.configure_retained_actions_publishing(
        "retained-actions/test/", publish_fn
    )

    dgb_context.persist_action("switch_7", "state", "off")

    publish_fn.assert_called_once_with(
        "retained-actions/test/switch_7/state", payload='"off"', qos=1, retain=True
    )


def test_publish_state_without_configuration_is_ignored(dgb_context):
    """Publishing does nothing until a topic and callback are configured."""
    dgb_context.persist_action("switch_1", "state", "on")


def test_publish_state_falls_back_to_string_for_unserializable_args(dgb_context):
    """Unserializable state arguments are published using their string form."""
    publish_fn = MagicMock()
    dgb_context.configure_retained_actions_publishing(
        "retained-actions/test/", publish_fn
    )
    args = {"value": object()}

    dgb_context.persist_action("switch_1", "state", args)

    publish_fn.assert_called_once_with(
        "retained-actions/test/switch_1/state", payload=str(args), qos=1, retain=True
    )


def test_publish_state_swallows_publish_errors(dgb_context):
    """Publish callback errors are logged without escaping."""
    publish_fn = MagicMock(side_effect=RuntimeError("publish failed"))
    dgb_context.configure_retained_actions_publishing(
        "retained-actions/test/", publish_fn
    )

    dgb_context.persist_action("switch_1", "state", "on")

    publish_fn.assert_called_once()


# ---------------------------------------------------------------------------
# Level 1: Binder Queue Management
# ---------------------------------------------------------------------------


def test_put_to_binder_queue(dgb_context):
    """Test putting messages into binder queue"""
    dgb_context.put_to_binder_queue("event", {"data": "test"})

    msg = dgb_context.binder_queue.get_nowait()
    assert isinstance(msg, BinderMessage)
    assert msg.cmd == "event"
    assert msg.payload == {"data": "test"}


def test_put_ruleset_command(dgb_context):
    """Test putting ruleset command"""
    dgb_context.put_to_binder_queue("ruleset", {"ruleset": "rs1"})

    msg = dgb_context.binder_queue.get_nowait()
    assert msg.cmd == "ruleset"
    assert msg.payload == {"ruleset": "rs1"}


# ---------------------------------------------------------------------------
# Level 2: Error Semantics - Close/Shutdown
# ---------------------------------------------------------------------------


def test_close_context(dgb_context):
    """Test closing context sends shutdown message"""
    dgb_context.close()

    assert dgb_context._closed is True
    msg = dgb_context.binder_queue.get_nowait()
    assert msg.cmd == "shutdown"


def test_close_idempotent(dgb_context):
    """Test that closing twice only sends one shutdown message"""
    dgb_context.close()
    dgb_context.close()

    # Should have exactly one shutdown message
    msg = dgb_context.binder_queue.get_nowait()
    assert msg.cmd == "shutdown"

    with pytest.raises(queue.Empty):
        dgb_context.binder_queue.get_nowait()


def test_cannot_put_message_after_close(dgb_context):
    """Test that putting non-shutdown message after close raises RuntimeError"""
    dgb_context.close()

    with pytest.raises(RuntimeError):
        dgb_context.put_to_binder_queue("event", {"data": "test"})


def test_shutdown_allowed_after_close(dgb_context):
    """Test that shutdown command is allowed after close"""
    dgb_context.close()
    # This should not raise
    dgb_context.put_to_binder_queue("shutdown", {})


def test_exit_calls_close(dgb_context):
    """Test that __exit__ calls close"""
    dgb_context.__exit__(None, None, None)

    assert dgb_context._closed is True


# ---------------------------------------------------------------------------
# Level 2: Edge Cases - Input Validation
# ---------------------------------------------------------------------------


def test_add_device_with_empty_functions(dgb_context):
    """Test adding device with empty functions dict"""
    dgb_context.add_object("dev1", {}, operations={})

    assert dgb_context.get_operations("dev1") == {}


def test_add_binding_empty_ruleset_name(dgb_context):
    """Test adding binding with empty ruleset name is still added"""
    dgb_context.add_binding("dev1", "")

    bindings = dgb_context.get_bindings("dev1")
    assert "" in bindings


def test_normalize_ruleset_with_multiple_dollar_signs(dgb_context):
    """Test normalization handles multiple dollar signs correctly"""
    dgb_context.add_binding("dev1", "ruleset$extra$more")

    bindings = dgb_context.get_bindings("dev1")
    assert "ruleset" in bindings
    assert "ruleset$extra$more" not in bindings


def test_put_to_config_queue(dgb_context):
    """Test putting messages into config queue."""
    dgb_context.put_to_config_queue("apply", {"Devices": []})

    msg = dgb_context.config_queue.get_nowait()
    assert isinstance(msg, ConfigMessage)
    assert msg.cmd == "apply"
    assert msg.payload == {"Devices": []}


def test_put_config_shutdown_command(dgb_context):
    """Test putting config shutdown command."""
    dgb_context.put_to_config_queue("shutdown", {})

    msg = dgb_context.config_queue.get_nowait()
    assert msg.cmd == "shutdown"
    assert msg.payload == {}


# ---------------------------------------------------------------------------
# Level 1: Stage 5 - Retained shadow state store
# ---------------------------------------------------------------------------


def test_record_retained_call(dgb_context):
    dgb_context.record_retained_action("switch_one", "payload", {"state": "on"})

    retained = dgb_context.get_object("switch_one").retained_actions
    assert retained == {"payload": {"state": "on"}}


def test_get_retained_call_object_is_none_when_missing(dgb_context):
    assert dgb_context.get_object("unknown") is None
