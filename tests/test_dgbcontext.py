import pytest
import queue

from DGB.DGBContext import DGBContext, BinderMessage


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
    dgb_context.add_device("relay1", device_obj)

    assert dgb_context.get_device("relay1") == device_obj
    assert dgb_context.get_functions("relay1") == {}


def test_add_device_with_functions(dgb_context):
    """Test adding a device with functions"""
    device_obj = {"type": "relay"}
    functions = {"on": lambda: True, "off": lambda: False}
    dgb_context.add_device("relay1", device_obj, functions=functions)

    assert dgb_context.get_device("relay1") == device_obj
    assert dgb_context.get_functions("relay1") == functions


def test_get_nonexistent_device(dgb_context):
    """Test getting a non-existent device returns None"""
    assert dgb_context.get_device("nonexistent") is None


# ---------------------------------------------------------------------------
# Level 1: Pin Management
# ---------------------------------------------------------------------------


def test_add_pin_without_functions(dgb_context):
    """Test adding a pin without functions"""
    pin_obj = {"pin": 17, "mode": "OUT"}
    dgb_context.add_pin("gpio17", pin_obj)

    assert dgb_context.get_pin("gpio17") == pin_obj
    assert dgb_context.get_functions("gpio17") == {}


def test_add_pin_with_functions(dgb_context):
    """Test adding a pin with functions"""
    pin_obj = {"pin": 17, "mode": "OUT"}
    functions = {"set_high": lambda: None, "set_low": lambda: None}
    dgb_context.add_pin("gpio17", pin_obj, functions=functions)

    assert dgb_context.get_pin("gpio17") == pin_obj
    assert dgb_context.get_functions("gpio17") == functions


def test_get_nonexistent_pin(dgb_context):
    """Test getting a non-existent pin returns None"""
    assert dgb_context.get_pin("nonexistent") is None


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
    dgb_context.add_device("dev1", {}, functions=functions)

    assert dgb_context.get_functions("dev1") == functions


def test_get_functions_from_pin(dgb_context):
    """Test getting functions from a pin"""
    functions = {"set": lambda: True}
    dgb_context.add_pin("pin1", {}, functions=functions)

    assert dgb_context.get_functions("pin1") == functions


# TODO: this test should fail in the future!!!
def test_get_functions_device_takes_precedence(dgb_context):
    """Test that device functions are returned over pin functions"""
    dev_functions = {"on": lambda: "device"}
    pin_functions = {"on": lambda: "pin"}
    dgb_context.add_device("id1", {}, functions=dev_functions)
    dgb_context.add_pin("id1", {}, functions=pin_functions)

    # Device should take precedence
    assert dgb_context.get_functions("id1") == dev_functions


def test_get_functions_nonexistent(dgb_context):
    """Test getting functions for non-existent device/pin returns empty dict"""
    assert dgb_context.get_functions("nonexistent") == {}


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
    dgb_context.add_device("dev1", {}, functions={})

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
