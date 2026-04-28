import pytest
from types import SimpleNamespace

from DGB.Binder import Binder


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


class DummyDGBContext:
    def __init__(self):
        self._functions = {}

    def get_functions(self, device_id):
        return self._functions.get(device_id, {})


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
# level 1: simpele functional tests
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


# ---------------------------------------------------------------------------
# level 2: error-semantics
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


def test_device_action_wrong_value_raises_value_error(binder, dgb_context):
    with pytest.raises(ValueError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": 1, "call": "do"}},
        )
    with pytest.raises(ValueError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "dev1", "call": 1}},
        )


def test_device_action_missing_device_raises_key_error(binder, dgb_context):
    with pytest.raises(KeyError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "missing", "call": "do"}},
        )


def test_device_action_missing_call_raises_key_error(binder, dgb_context):
    dgb_context._functions["dev1"] = {}

    with pytest.raises(KeyError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"action": {"unique_id": "dev1", "call": "do"}},
        )


def test_timer_start_missing_seconds_raises_value_error(binder):
    with pytest.raises(ValueError):
        binder.build_action(
            "ruleset1",
            "rule1",
            {"timer": {"name": "t1", "action": "start"}},
        )


# ---------------------------------------------------------------------------
# level 1: condition handler
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
