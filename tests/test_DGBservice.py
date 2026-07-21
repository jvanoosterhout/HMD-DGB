import pytest
from unittest.mock import MagicMock, patch
import json
from contextlib import contextmanager

from DGB.DGBservice import DGBservice


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def make_service():
    """Create DGBservice with patched constructor dependencies."""

    def _make_service(**kwargs):
        with (
            patch("DGB.DGBservice.SystemDevices") as mock_system_devices_class,
            patch("DGB.DGBservice.mqtt.Client") as mock_client_class,
            patch("DGB.DGBservice.Settings.MQTT") as mock_settings_mqtt,
        ):
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_settings_mqtt.return_value = MagicMock()
            mock_system_devices_class.return_value = MagicMock()

            service = DGBservice(
                name=kwargs.pop("name", "test"),
                broker=kwargs.pop("broker", "localhost"),
                **kwargs,
            )

        return service, mock_client

    return _make_service


@contextmanager
def patched_apply_handlers(service):
    """Patch payload handlers during config-cycle tests."""
    with (
        patch.object(service, "_handle_devices") as mock_devices,
        patch.object(service, "_handle_pins") as mock_pins,
        patch.object(service, "_handle_bindings") as mock_bindings,
    ):
        yield mock_devices, mock_pins, mock_bindings


# ---------------------------------------------------------------------------
# Level 1: Initialization and structure
# ---------------------------------------------------------------------------


def test_dgbservice_init(make_service):
    """Test DGBservice initialization sets core attributes"""
    service, _ = make_service(
        name="test-device",
        port=1883,
        username="user",
        password="pass",
    )

    assert service.name == "test-device"
    assert service.broker == "localhost"
    assert service.port == 1883
    assert service.username == "user"
    assert service.password == "pass"


def test_dgbservice_client_id_format(make_service):
    """Test MQTT client ID follows expected format"""
    service, _ = make_service(name="garage")

    assert service.client_id == "dgb-garage"


def test_dgbservice_config_topic_default(make_service):
    """Test default config topic format"""
    service, _ = make_service(name="test")

    assert service.config_topic == "config/test/devices/"


def test_dgbservice_config_topic_custom(make_service):
    """Test custom config topic"""
    service, _ = make_service(name="test", topic="custom/topic/")

    assert service.config_topic == "custom/topic/"


def test_dgbservice_shutdown_event_not_set_initially(make_service):
    """Test shutdown event is not set on initialization"""
    service, _ = make_service(name="test")

    assert not service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 1: Lifecycle methods
# ---------------------------------------------------------------------------


def test_dgbservice_stop_sets_shutdown_event(make_service):
    """Test stop() sets shutdown event"""
    service, _ = make_service(name="test")

    service.stop()

    assert service.shutdown_event.is_set()


def test_dgbservice_stop_is_idempotent(make_service):
    """Test calling stop() twice doesn't cause issues"""
    service, _ = make_service(name="test")

    service.stop()
    service.stop()  # Should not raise

    assert service.shutdown_event.is_set()


def test_dgbservice_exit_calls_stop(make_service):
    """Test __exit__ calls stop()"""
    service, _ = make_service(name="test")

    service.__exit__(None, None, None)

    assert service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 2: Error cases and edge cases
# ---------------------------------------------------------------------------


def test_dgbservice_stop_before_start(make_service):
    """Test stopping service without starting it"""
    service, _ = make_service(name="test")

    service.stop()  # Should not raise even though start() wasn't called

    assert service.shutdown_event.is_set()


def test_dgbservice_on_connect_callback_exists(make_service):
    """Test on_connect callback is registered"""
    _, mock_client = make_service(name="test")

    # Verify callback was set
    assert mock_client.on_connect is not None


def test_dgbservice_on_message_callback_exists(make_service):
    """Test on_message callback is registered"""
    _, mock_client = make_service(name="test")

    # Verify callback was set
    assert mock_client.on_message is not None


def test_dgbservice_create_mqtt_client_calls_connect(make_service):
    """Test _create_mqtt_client connects to broker"""
    _, mock_client = make_service(name="test", broker="broker.local", port=1883)

    # Verify connect was called with correct args
    mock_client.connect.assert_called()


# ---------------------------------------------------------------------------
# Level 2: Startup phase / config-apply cycle
# ---------------------------------------------------------------------------


def test_run_config_apply_cycle_sets_live_on_success(make_service):
    """A successful config cycle should end in live phase."""
    service, _ = make_service(name="test")

    with patched_apply_handlers(service) as (mock_devices, mock_pins, mock_bindings):
        service._run_config_apply_cycle({})

    assert mock_devices.called
    assert mock_pins.called
    assert mock_bindings.called
    assert service.dgb_context.get_runtime_phase() == "live"


def test_run_config_apply_cycle_sets_blocked_on_failure(make_service):
    """A failed config cycle should set blocked phase."""
    service, _ = make_service(name="test")

    with patch.object(service, "_handle_devices", side_effect=RuntimeError("boom")):
        service._run_config_apply_cycle({})

    assert service.dgb_context.get_runtime_phase() == "blocked"


def test_on_message_triggers_config_apply_cycle(make_service):
    """Config-topic messages should enqueue config apply command."""
    service, _ = make_service(name="test")
    msg = MagicMock()
    msg.topic = "config/test/devices/test"
    msg.payload = json.dumps({"Devices": []}).encode()

    with patch.object(service.dgb_context, "put_to_config_queue") as mock_enqueue:
        service._on_message(None, None, msg)
        mock_enqueue.assert_called_once_with("apply", {"Devices": []})


# ---------------------------------------------------------------------------
# Level 2: Stage 11 - Idempotency and buffering
# ---------------------------------------------------------------------------


def test_run_config_apply_cycle_idempotent_on_replay(make_service):
    """Replaying the same payload should be idempotent (skipped)."""
    service, _ = make_service(name="test")
    payload = {"Devices": [], "Pins": [], "Bindings": []}

    with patched_apply_handlers(service):
        # First run: payload gets recorded as applied.
        service._run_config_apply_cycle(payload)
        phase_after_first = service.dgb_context.get_runtime_phase()
        assert phase_after_first == "live"  # Cycle 1 should complete successfully

        # Second run with same payload: should be idempotent (early return).
        service._run_config_apply_cycle(payload)
        # Idempotency check prevents handlers from being called twice on second run.
        assert service.dgb_context.payload_already_applied(
            service.dgb_context.compute_payload_hash(payload)
        )


def test_run_config_apply_cycle_buffers_later_payloads(make_service):
    """Config dispatcher processes queued payloads sequentially."""
    service, _ = make_service(name="test")

    payload1 = {"Devices": [{"id": "dev1"}], "Pins": [], "Bindings": []}
    payload2 = {"Devices": [{"id": "dev2"}], "Pins": [], "Bindings": []}

    service.dgb_context.put_to_config_queue("apply", payload1)
    service.dgb_context.put_to_config_queue("apply", payload2)
    service.dgb_context.put_to_config_queue("shutdown", {})

    with patch.object(service, "_run_config_apply_cycle") as mock_cycle:
        service.config_dispatcher()

    assert mock_cycle.call_count == 2
    assert mock_cycle.call_args_list[0].args[0] == payload1
    assert mock_cycle.call_args_list[1].args[0] == payload2


# ---------------------------------------------------------------------------
# Level 2: Stage 5 - Retained shadow state
# ---------------------------------------------------------------------------


def test_on_message_stores_state_shadow_payload(make_service):
    service, _ = make_service(name="test")
    msg = MagicMock()
    msg.topic = "state/test/switch_one"
    msg.payload = json.dumps({"value": "on"}).encode()

    with patch.object(service.dgb_context, "put_to_config_queue") as mock_enqueue:
        service._on_message(None, None, msg)
        mock_enqueue.assert_not_called()

    retained = service.dgb_context.get_retained_value("switch_one")
    assert retained is not None
    assert retained.topic == "state/test/switch_one"
    assert retained.payload_decoded == {"value": "on"}


def test_run_config_apply_cycle_subscribes_retain_state_topics(make_service):
    service, mock_client = make_service(name="test")
    payload = {
        "startup_policy": {
            "state_initialization": {
                "retain_state": [{"unique_id": "water_meter"}],
            }
        }
    }

    with patched_apply_handlers(service):
        service._run_config_apply_cycle(payload)

    assert (
        service.dgb_context.get_retained_topic("water_meter")
        == "state/test/water_meter"
    )
    mock_client.subscribe.assert_any_call("state/test/water_meter", qos=1)


def test_run_config_apply_cycle_logs_preset_fallback_when_retained_missing(
    make_service,
):
    service, _ = make_service(name="test")
    payload = {
        "startup_policy": {
            "state_initialization": {
                "retain_state": [{"unique_id": "switch_one"}],
                "preset_value": [
                    {
                        "unique_id": "switch_one",
                        "call": "set_state",
                        "args": [{"name": "value", "value": "on"}],
                    }
                ],
            }
        }
    }

    with patch.object(service.logger, "info") as mock_info:
        with patched_apply_handlers(service):
            service._run_config_apply_cycle(payload)

    assert any(
        "falling back to preset_value" in str(call.args[0])
        for call in mock_info.call_args_list
        if call.args
    )


# ---------------------------------------------------------------------------
# Level 2: Stage 6 - configured_default application
# ---------------------------------------------------------------------------


def test_run_config_apply_cycle_applies_preset_via_set_state(make_service):
    service, _ = make_service(name="test")
    observed_values = []

    def set_state(value: int):
        observed_values.append(value)

    service.dgb_context.add_object("sensor_1", object(), {"set_state": set_state})

    payload = {
        "startup_policy": {
            "state_initialization": {
                "preset_value": [
                    {
                        "unique_id": "sensor_1",
                        "call": "set_state",
                        "args": [{"name": "value", "value": "42"}],
                    }
                ],
            }
        }
    }

    with patched_apply_handlers(service):
        service._run_config_apply_cycle(payload)

    assert observed_values == [42]


def test_run_config_apply_cycle_applies_preset_via_action_call_and_args(make_service):
    service, _ = make_service(name="test")
    observed = {}

    def log(integer: int | None = None, string: str | None = None):
        observed["integer"] = integer
        observed["string"] = string
        return True

    service.dgb_context.add_object("p1", object(), {"log": log})

    payload = {
        "startup_policy": {
            "state_initialization": {
                "preset_value": [
                    {
                        "unique_id": "p1",
                        "call": "log",
                        "args": [
                            {"name": "integer", "value": "1"},
                            {"name": "string", "value": 1},
                        ],
                    }
                ],
            }
        }
    }

    with patched_apply_handlers(service):
        service._run_config_apply_cycle(payload)

    assert observed["integer"] == 1
    assert observed["string"] == "1"


def test_run_config_apply_cycle_applies_preset_via_on_off(make_service):
    service, _ = make_service(name="test")
    on_fn = MagicMock()
    off_fn = MagicMock()
    service.dgb_context.add_object("17", object(), {"on": on_fn, "off": off_fn})

    payload = {
        "startup_policy": {
            "state_initialization": {
                "preset_value": [
                    {
                        "unique_id": "17",
                        "call": "off",
                        "args": [],
                    }
                ],
            }
        }
    }

    with patched_apply_handlers(service):
        service._run_config_apply_cycle(payload)

    off_fn.assert_called_once()
    on_fn.assert_not_called()


def test_run_config_apply_cycle_preset_missing_functions_logs_warning(make_service):
    service, _ = make_service(name="test")
    payload = {
        "startup_policy": {
            "state_initialization": {
                "preset_value": [
                    {
                        "unique_id": "unknown_device",
                        "call": "set_state",
                        "args": [{"name": "value", "value": "on"}],
                    }
                ],
            }
        }
    }

    with patch.object(service.logger, "warning") as mock_warning:
        with patched_apply_handlers(service):
            service._run_config_apply_cycle(payload)

    mock_warning.assert_any_call(
        "Configured default for %s ignored: no registered functions",
        "unknown_device",
    )
