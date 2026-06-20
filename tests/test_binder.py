import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import threading

from DGB.Binder import Binder, TimerRegistry, iter_parents


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


class DummyDGBContext:
    def __init__(self):
        self._functions = {}
        self._devices = {}
        self._pins = {}
        self.engine_lock = threading.Lock()
        self.bindings = {}

    def get_functions(self, device_id):
        return self._functions.get(device_id, {})

    def get_device(self, device_id):
        return self._devices.get(device_id)

    def get_pin(self, pin_id):
        return self._pins.get(pin_id)

    def add_binding(self, device_id, ruleset_name):
        if device_id not in self.bindings:
            self.bindings[device_id] = set()
        self.bindings[device_id].add(ruleset_name)

    def get_bindings(self, device_id):
        return self.bindings.get(device_id, set())

    def put_to_binder_queue(self, cmd, payload):
        pass


class DummyContext:
    """Minimal context with only what Binder needs"""

    def __init__(self):
        self.s = SimpleNamespace(return_value=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dgb_context():
    return DummyDGBContext()


@pytest.fixture
def binder(dgb_context):
    return Binder(dgb_context=dgb_context)


# ---------------------------------------------------------------------------
# Level 1: Timer Registry Tests
# ---------------------------------------------------------------------------


def test_timer_registry_start_creates_and_stores_timer():
    """Test that timer registry starts a timer and stores it"""
    mock_timer_factory = MagicMock()
    mock_timer = MagicMock()
    mock_timer_factory.return_value = mock_timer

    registry = TimerRegistry(timer_factory=mock_timer_factory)
    callback = MagicMock()

    registry.start("timer1", 5.0, callback)

    mock_timer_factory.assert_called_once_with(5.0, callback)
    mock_timer.start.assert_called_once()


def test_timer_registry_cancel_returns_true_when_exists():
    """Test that canceling existing timer returns True"""
    mock_timer_factory = MagicMock()
    mock_timer = MagicMock()
    mock_timer_factory.return_value = mock_timer

    registry = TimerRegistry(timer_factory=mock_timer_factory)
    registry.start("timer1", 5.0, MagicMock())

    result = registry.cancel("timer1")

    assert result is True
    mock_timer.cancel.assert_called_once()


def test_timer_registry_cancel_returns_false_when_not_exists():
    """Test that canceling non-existent timer returns False"""
    registry = TimerRegistry()
    result = registry.cancel("nonexistent")
    assert result is False


def test_timer_registry_cancel_then_start_replaces_timer():
    """Test that starting a timer replaces an existing one"""
    mock_timer_factory = MagicMock()
    timers = [MagicMock(), MagicMock()]
    mock_timer_factory.side_effect = timers

    registry = TimerRegistry(timer_factory=mock_timer_factory)
    registry.start("timer1", 5.0, MagicMock())
    registry.start("timer1", 10.0, MagicMock())

    # First timer should be canceled
    timers[0].cancel.assert_called_once()
    # Both timers should be started
    assert timers[0].start.called
    assert timers[1].start.called


# ---------------------------------------------------------------------------
# Level 1: iter_parents Helper Tests
# ---------------------------------------------------------------------------


def test_iter_parents_finds_key_in_flat_dict():
    """Test finding key in flat dictionary"""
    tree = {"a": 1, "b": 2}
    results = list(iter_parents(tree, "a"))
    assert len(results) > 0
    assert results[0] == (("a",), tree)


def test_iter_parents_finds_key_in_nested_dict():
    """Test finding key in nested dictionary"""
    tree = {"outer": {"inner": 5}}
    results = list(iter_parents(tree, "inner"))
    assert any(path == ("outer", "inner") for path, _ in results)


def test_iter_parents_finds_key_in_list():
    """Test finding key in list of dicts"""
    tree = {"items": [{"id": 1}, {"id": 2}]}
    results = list(iter_parents(tree, "id"))
    # Should find id in both list items
    assert len(results) >= 2


def test_iter_parents_ignores_strings():
    """Test that strings are not recursed into"""
    tree = {"text": "hello"}
    results = list(iter_parents(tree, "h"))
    # Should not find 'h' inside the string
    assert all("h" not in path for path, _ in results)


# ---------------------------------------------------------------------------
# Level 1: Simple functional tests
# ---------------------------------------------------------------------------


def test_build_log_action(binder):
    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"log": {"msg": "hello"}},
    )

    ctx = DummyContext()
    action(ctx)  # should not raise


def test_build_device_action_success(binder, dgb_context):
    called = {"ok": False}

    def fn():
        called["ok"] = True
        return True

    dgb_context._functions["dev1"] = {"do": fn}

    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"action": {"unique_id": "dev1", "call": "do"}},
    )

    ctx = DummyContext()
    action(ctx)

    assert called["ok"] is True
    assert ctx.s.return_value == {"value": True}


def test_build_device_action_with_return_false(binder, dgb_context):
    """Test device action sets return_value to False when function returns False"""

    def fn():
        return False

    dgb_context._functions["dev1"] = {"do": fn}

    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"action": {"unique_id": "dev1", "call": "do"}},
    )

    ctx = DummyContext()
    action(ctx)

    assert ctx.s.return_value == {"value": False}


def test_build_device_action_with_return_none(binder, dgb_context):
    """Test device action sets return_value to True when function returns None"""

    def fn():
        return None

    dgb_context._functions["dev1"] = {"do": fn}

    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"action": {"unique_id": "dev1", "call": "do"}},
    )

    ctx = DummyContext()
    action(ctx)

    assert ctx.s.return_value == {"value": True}


def test_build_timer_start_action(binder, dgb_context):
    """Test building timer start action"""
    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"timer": {"name": "timer1", "action": "start", "seconds": 5.0}},
    )

    assert action is not None
    assert callable(action)


def test_build_timer_cancel_action(binder, dgb_context):
    """Test building timer cancel action"""
    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"timer": {"name": "timer1", "action": "cancel"}},
    )

    assert action is not None
    assert callable(action)


# ---------------------------------------------------------------------------
# Level 2: Error semantics
# ---------------------------------------------------------------------------


def test_log_action_wrong_value_raises_value_error(binder):
    with pytest.raises(ValueError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"log": {"msg": 1}},
        )


def test_unknown_action_type_raises_value_error(binder):
    with pytest.raises(ValueError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"unknown": {"x": "1"}},
        )


def test_device_action_wrong_unique_id_raises_value_error(binder, dgb_context):
    """Test device action with non-string unique_id raises ValueError"""
    with pytest.raises(ValueError, match="unique_id must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": 1, "call": "do"}},
        )


def test_device_action_empty_unique_id_raises_value_error(binder, dgb_context):
    """Test device action with empty unique_id raises ValueError"""
    with pytest.raises(ValueError, match="unique_id must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "", "call": "do"}},
        )


def test_device_action_wrong_call_raises_value_error(binder, dgb_context):
    """Test device action with non-string call raises ValueError"""
    with pytest.raises(ValueError, match="call must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "dev1", "call": 1}},
        )


def test_device_action_empty_call_raises_value_error(binder, dgb_context):
    """Test device action with empty call raises ValueError"""
    with pytest.raises(ValueError, match="call must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "dev1", "call": ""}},
        )


def test_device_action_missing_device_raises_key_error(binder, dgb_context):
    with pytest.raises(KeyError, match="No action function"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "missing", "call": "do"}},
        )


def test_device_action_missing_call_raises_key_error(binder, dgb_context):
    dgb_context._functions["dev1"] = {}

    with pytest.raises(KeyError, match="No action function"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "dev1", "call": "do"}},
        )


def test_timer_start_missing_seconds_raises_value_error(binder):
    """Test timer start without seconds raises ValueError"""
    with pytest.raises(ValueError, match="Unknown action definition"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"timer": {"name": "t1", "action": "start"}},
        )


def test_timer_start_none_seconds_raises_value_error(binder):
    """Test timer start with None seconds raises ValueError"""
    with pytest.raises(ValueError, match="timer.seconds required"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"timer": {"name": "t1", "action": "start", "seconds": None}},
        )


def test_timer_start_invalid_name_raises_value_error(binder):
    """Test timer start with invalid name raises ValueError"""
    with pytest.raises(ValueError, match="timer.name must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"timer": {"name": "", "action": "start", "seconds": 5.0}},
        )


def test_timer_cancel_invalid_name_raises_value_error(binder):
    """Test timer cancel with invalid name raises ValueError"""
    with pytest.raises(ValueError, match="timer.name must be non-empty str"):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"timer": {"name": 123, "action": "cancel"}},
        )


# ---------------------------------------------------------------------------
# Level 1: Condition handler
# ---------------------------------------------------------------------------


def test_condition_handler_executes_actions(binder, dgb_context):
    called = {"ok": False}

    def fn():
        called["ok"] = True

    dgb_context._functions["dev1"] = {"do": fn}

    handler = binder.build_condition_handler(
        "ruleset1",
        "rule1",
        [
            {"log": {"msg": "hi"}},
            {"action": {"unique_id": "dev1", "call": "do"}},
        ],
    )

    ctx = DummyContext()
    handler(ctx)

    assert called["ok"] is True


def test_condition_handler_sets_return_value_pending(binder):
    """Test condition handler sets return_value to pending"""
    handler = binder.build_condition_handler(
        "ruleset1",
        "rule1",
        [{"log": {"msg": "hi"}}],
    )

    ctx = DummyContext()
    handler(ctx)

    assert ctx.s.return_value == {"value": "pending"}


def test_condition_handler_propagates_exceptions(binder, dgb_context):
    """Test that condition handler propagates action exceptions"""

    def failing_fn():
        raise ValueError("Test error")

    dgb_context._functions["dev1"] = {"do": failing_fn}

    handler = binder.build_condition_handler(
        "ruleset1",
        "rule1",
        [{"action": {"unique_id": "dev1", "call": "do"}}],
    )

    ctx = DummyContext()
    with pytest.raises(ValueError, match="Test error"):
        handler(ctx)


# ---------------------------------------------------------------------------
# Level 2: Device action with arguments
# ---------------------------------------------------------------------------


def test_device_action_with_arguments(binder, dgb_context):
    """Test device action passes arguments to function"""
    called_with = {}

    def fn(value=None):
        called_with["value"] = value
        return True

    dgb_context._functions["dev1"] = {"do": fn}

    action = binder.build_action(
        "ruleset1",
        "rule1",
        {
            "action": {
                "unique_id": "dev1",
                "call": "do",
                "args": [{"name": "value", "value": 42}],
            }
        },
    )

    ctx = DummyContext()
    action(ctx)

    assert called_with["value"] == 42


# ---------------------------------------------------------------------------
# Level 2: Timer action execution
# ---------------------------------------------------------------------------


def test_timer_start_action_execution(binder, dgb_context):
    """Test executing a timer start action"""
    mock_timer_factory = MagicMock()
    mock_timer = MagicMock()
    mock_timer_factory.return_value = mock_timer

    binder.timers = TimerRegistry(timer_factory=mock_timer_factory)

    action = binder.build_action(
        "ruleset1",
        "rule1",
        {"timer": {"name": "timer1", "action": "start", "seconds": 5.0}},
    )

    ctx = DummyContext()
    dgb_context.put_to_binder_queue = MagicMock()
    action(ctx)

    # Timer should have been created
    mock_timer_factory.assert_called_once()
    mock_timer.start.assert_called_once()


def test_timer_cancel_action_execution(binder, dgb_context):
    """Test executing a timer cancel action"""
    # Start a timer first
    mock_timer_factory = MagicMock()
    mock_timer = MagicMock()
    mock_timer_factory.return_value = mock_timer

    binder.timers = TimerRegistry(timer_factory=mock_timer_factory)

    start_action = binder.build_action(
        "ruleset1",
        "rule1",
        {"timer": {"name": "timer1", "action": "start", "seconds": 5.0}},
    )

    ctx = DummyContext()
    start_action(ctx)

    # Now cancel it
    cancel_action = binder.build_action(
        "ruleset1",
        "rule1",
        {"timer": {"name": "timer1", "action": "cancel"}},
    )

    cancel_action(ctx)

    # Timer should have been canceled
    mock_timer.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# Level 2: Event Dispatcher Tests
# ---------------------------------------------------------------------------


def test_handle_post_with_unique_id(binder, dgb_context):
    """Test _handle_post processes payload with unique_id"""
    dgb_context.add_binding("dev1", "ruleset1")

    with patch("DGB.Binder.post") as mock_post:
        binder._handle_post({"unique_id": "dev1", "data": "test"})
        mock_post.assert_called_once()


def test_handle_post_with_rulesetname(binder):
    """Test _handle_post processes payload with rulesetname"""
    with patch("DGB.Binder.post") as mock_post:
        binder._handle_post({"rulesetname": "ruleset1", "data": "test"})
        mock_post.assert_called_once()


def test_handle_post_missing_both_raises_error(binder):
    """Test _handle_post raises error when both unique_id and rulesetname missing"""
    with pytest.raises(ValueError, match="post payload requires"):
        binder._handle_post({"data": "test"})


def test_handle_post_with_missing_device_logs_warning(binder, dgb_context):
    """Test _handle_post logs warning for unregistered device"""
    with patch("DGB.Binder.post"):
        with patch.object(binder.logger, "warning") as mock_warning:
            binder._handle_post({"unique_id": "unknown_dev", "data": "test"})
            mock_warning.assert_called_once()


# ---------------------------------------------------------------------------
# Level 2: New Binding Tests
# ---------------------------------------------------------------------------


# def test_new_binding_registers_device(binder, dgb_context):
#     """Test new_binding registers devices with rulesets"""
#     dgb_context._devices["dev2"] = {"type": "relay"}

#     bind_config = {
#         "ruleset2": {
#             "all": [{"unique_id": "dev2"}],
#         }
#     }

#     with patch("DGB.Binder.get_host"):
#         binder.new_binding(bind_config)

#     # Device should be registered
#     assert "ruleset2" in dgb_context.get_bindings("dev2")


# def test_new_binding_missing_device_raises_error(binder, dgb_context):
#     """Test new_binding raises KeyError for unregistered device"""
#     bind_config = {
#         "ruleset3": {
#             "all": [{"unique_id": "missing_dev"}],
#         }
#     }

#     with patch("DGB.Binder.get_host"):
#         with pytest.raises(KeyError, match="Device.*not found"):
#             binder.new_binding(bind_config)


# def test_new_binding_registers_pins(binder, dgb_context):
#     """Test new_binding registers pins with rulesets"""
#     dgb_context._pins["pin1"] = {"pin": 17}

#     bind_config = {
#         "ruleset4": {
#             "all": [{"unique_id": "pin1"}],
#         }
#     }

#     with patch("DGB.Binder.get_host"):
#         binder.new_binding(bind_config)

#     # Pin should be registered
#     assert "ruleset4" in dgb_context.get_bindings("pin1")


# def test_new_binding_builds_condition_handlers(binder, dgb_context):
#     """Test new_binding builds condition handlers for run actions"""
#     dgb_context._devices["dev5"] = {"type": "relay"}
#     dgb_context._functions["dev5"] = {"activate": lambda: True}

#     bind_config = {
#         "ruleset5": {
#             "all": [{"unique_id": "dev5"}],
#             "run": [{"log": {"msg": "activated"}}],
#         }
#     }

#     with patch("DGB.Binder.get_host"):
#         binder.new_binding(bind_config)

#     # The run action should be replaced with a callable
#     assert callable(bind_config["ruleset5"]["run"])
