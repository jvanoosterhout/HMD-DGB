import pytest
import queue
from unittest.mock import MagicMock

from DGB.DGBContext import DGBContext, BinderMessage, ConfigMessage


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

    assert dgb_context.get_object("relay1") == device_obj
    assert dgb_context.get_functions("relay1") == {}


def test_add_device_with_functions(dgb_context):
    """Test adding a device with functions"""
    device_obj = {"type": "relay"}
    functions = {"on": lambda: True, "off": lambda: False}
    dgb_context.add_object("relay1", device_obj, functions=functions)

    assert dgb_context.get_object("relay1") == device_obj
    assert dgb_context.get_functions("relay1") == functions


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

    assert dgb_context.get_object("gpio17") == pin_obj
    assert dgb_context.get_functions("gpio17") == {}


def test_add_pin_with_functions(dgb_context):
    """Test adding a pin with functions"""
    pin_obj = {"pin": 17, "mode": "OUT"}
    functions = {"set_high": lambda: None, "set_low": lambda: None}
    dgb_context.add_object("gpio17", pin_obj, functions=functions)

    assert dgb_context.get_object("gpio17") == pin_obj
    assert dgb_context.get_functions("gpio17") == functions


def test_get_nonexistent_pin(dgb_context):
    """Test getting a non-existent pin returns None"""
    assert dgb_context.get_object("nonexistent") is None


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


def test_get_functions_from_device(dgb_context):
    """Test getting functions from a device"""
    functions = {"on": lambda: True}
    dgb_context.add_object("dev1", {}, functions=functions)

    assert dgb_context.get_functions("dev1") == functions


def test_get_functions_from_pin(dgb_context):
    """Test getting functions from a pin"""
    functions = {"set": lambda: True}
    dgb_context.add_object("pin1", {}, functions=functions)

    assert dgb_context.get_functions("pin1") == functions


def test_get_functions_last_write_wins(dgb_context):
    """Unified object model: latest registration for a unique_id wins."""
    dev_functions = {"on": lambda: "device"}
    pin_functions = {"on": lambda: "pin"}
    dgb_context.add_object("id1", {}, functions=dev_functions)
    dgb_context.add_object("id1", {}, functions=pin_functions)

    assert dgb_context.get_functions("id1") == pin_functions


def test_get_functions_nonexistent(dgb_context):
    """Test getting functions for non-existent device/pin returns empty dict"""
    assert dgb_context.get_functions("nonexistent") == {}


def test_retained_value_updates_dgb_object_state_store(dgb_context):
    dgb_context.record_retained_state("switch_2", "state", "on")

    retained = dgb_context.get_retained_state("switch_2")
    assert retained == {"state": "on"}
    assert dgb_context.get_retained_state("switch_2") == {"state": "on"}


def test_publish_state_value_calls_publish_fn(dgb_context):
    publish_fn = MagicMock()
    dgb_context.configure_retained_state_publishing("state/test/", publish_fn)

    dgb_context.publish_state_value("switch_7", "state", "off")

    publish_fn.assert_called_once_with(
        "state/test/switch_7/state", payload='"off"', qos=1, retain=True
    )


# ---------------------------------------------------------------------------
# Level 1: Binder Queue Management
# ---------------------------------------------------------------------------


def test_put_to_binder_queue(dgb_context):
    """Test putting messages into binder queue"""
    dgb_context.put_to_binder_queue("post", {"data": "test"})

    msg = dgb_context.binder_queue.get_nowait()
    assert isinstance(msg, BinderMessage)
    assert msg.cmd == "post"
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
        dgb_context.put_to_binder_queue("post", {"data": "test"})


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
    dgb_context.add_object("dev1", {}, functions={})

    assert dgb_context.get_functions("dev1") == {}


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


# ---------------------------------------------------------------------------
# Level 1: Runtime phase / config apply cycle
# ---------------------------------------------------------------------------


def test_runtime_phase_defaults_to_live(dgb_context):
    """Default phase is live for backward compatibility."""
    assert dgb_context.get_runtime_phase() == "live"
    assert dgb_context.is_live_dispatch_enabled() is True


def test_begin_config_apply_cycle_sets_creation_phase(dgb_context):
    """Starting a config cycle increments id and enters creation phase."""
    cycle = dgb_context.begin_config_apply_cycle()

    assert cycle == 1
    assert dgb_context.get_config_apply_cycle_id() == 1
    assert dgb_context.get_runtime_phase() == "creation"
    assert dgb_context.is_live_dispatch_enabled() is False


def test_set_runtime_phase_roundtrip(dgb_context):
    """Runtime phase can be changed explicitly."""
    dgb_context.set_runtime_phase("apply")
    assert dgb_context.get_runtime_phase() == "apply"
    assert dgb_context.is_live_dispatch_enabled() is False

    dgb_context.set_runtime_phase("live")
    assert dgb_context.get_runtime_phase() == "live"
    assert dgb_context.is_live_dispatch_enabled() is True


# ---------------------------------------------------------------------------
# Level 1: Stage 11 - Buffering and idempotency
# ---------------------------------------------------------------------------


def test_payload_hash_idempotency(dgb_context):
    """Payload hash dedup works correctly."""
    payload = {"Devices": [], "Pins": []}
    hash1 = dgb_context.compute_payload_hash(payload)

    assert dgb_context.payload_already_applied(hash1) is False

    dgb_context.record_payload_hash(hash1)

    assert dgb_context.payload_already_applied(hash1) is True


def test_payload_hash_different_payloads(dgb_context):
    """Different payloads produce different hashes."""
    payload1 = {"Devices": [], "Pins": []}
    payload2 = {"Devices": [{"id": "1"}], "Pins": []}

    hash1 = dgb_context.compute_payload_hash(payload1)
    hash2 = dgb_context.compute_payload_hash(payload2)

    assert hash1 != hash2


def test_payload_hash_deterministic(dgb_context):
    """Same payload produces same hash (deterministic)."""
    payload = {"Devices": [{"id": "1"}], "Pins": [{"pin": 17}]}

    hash1 = dgb_context.compute_payload_hash(payload)
    hash2 = dgb_context.compute_payload_hash(payload)

    assert hash1 == hash2


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


def test_record_and_get_retained_state(dgb_context):
    dgb_context.record_retained_state("switch_one", "payload", {"value": "on"})

    assert dgb_context.has_retained_value("switch_one") is True
    assert dgb_context.get_retained_state("switch_one") == {"payload": {"value": "on"}}
    assert dgb_context.get_retained_state("switch_one") == {"payload": {"value": "on"}}


def test_has_retained_value_false_when_missing(dgb_context):
    assert dgb_context.has_retained_value("unknown") is False
    assert dgb_context.get_retained_state("unknown") == {}
