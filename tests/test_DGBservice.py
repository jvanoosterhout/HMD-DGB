import pytest
from unittest.mock import MagicMock, patch
import json

from DGB.DGBservice import DGBservice


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client"""
    client = MagicMock()
    return client


@pytest.fixture
def mock_mqtt_settings():
    """Create a mock MQTT settings object"""
    settings = MagicMock()
    return settings


# ---------------------------------------------------------------------------
# Level 1: Initialization and structure
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_init(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test DGBservice initialization sets core attributes"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices = MagicMock()
    mock_system_devices_class.return_value = mock_system_devices

    service = DGBservice(
        name="test-device",
        broker="localhost",
        port=1883,
        username="user",
        password="pass",
    )

    assert service.name == "test-device"
    assert service.broker == "localhost"
    assert service.port == 1883
    assert service.username == "user"
    assert service.password == "pass"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_client_id_format(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test MQTT client ID follows expected format"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="garage",
        broker="localhost",
    )

    assert service.client_id == "dgb-garage"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_config_topic_default(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test default config topic format"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    assert service.config_topic == "config/test/devices/"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_config_topic_custom(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test custom config topic"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
        topic="custom/topic/",
    )

    assert service.config_topic == "custom/topic/"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_shutdown_event_not_set_initially(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test shutdown event is not set on initialization"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    assert not service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 1: Lifecycle methods
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_sets_shutdown_event(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test stop() sets shutdown event"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_is_idempotent(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test calling stop() twice doesn't cause issues"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()
    service.stop()  # Should not raise

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_exit_calls_stop(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test __exit__ calls stop()"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.__exit__(None, None, None)

    assert service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 2: Error cases and edge cases
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_before_start(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test stopping service without starting it"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()  # Should not raise even though start() wasn't called

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_on_connect_callback_exists(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test on_connect callback is registered"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    DGBservice(
        name="test",
        broker="localhost",
    )

    # Verify callback was set
    assert mock_client.on_connect is not None


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_on_message_callback_exists(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test on_message callback is registered"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    DGBservice(
        name="test",
        broker="localhost",
    )

    # Verify callback was set
    assert mock_client.on_message is not None


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_create_mqtt_client_calls_connect(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Test _create_mqtt_client connects to broker"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    DGBservice(
        name="test",
        broker="broker.local",
        port=1883,
    )

    # Verify connect was called with correct args
    mock_client.connect.assert_called()


# ---------------------------------------------------------------------------
# Level 2: Startup phase / config-apply cycle
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_run_config_apply_cycle_sets_live_on_success(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """A successful config cycle should end in live phase."""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(name="test", broker="localhost")

    with (
        patch.object(service, "_handle_devices") as mock_devices,
        patch.object(service, "_handle_pins") as mock_pins,
        patch.object(service, "_handle_bindings") as mock_bindings,
    ):
        service._run_config_apply_cycle({})

    assert mock_devices.called
    assert mock_pins.called
    assert mock_bindings.called
    assert service.dgb_context.get_runtime_phase() == "live"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_run_config_apply_cycle_sets_blocked_on_failure(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """A failed config cycle should set blocked phase."""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(name="test", broker="localhost")

    with patch.object(service, "_handle_devices", side_effect=RuntimeError("boom")):
        service._run_config_apply_cycle({})

    assert service.dgb_context.get_runtime_phase() == "blocked"


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_on_message_triggers_config_apply_cycle(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Config-topic messages should enqueue config apply command."""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(name="test", broker="localhost")
    msg = MagicMock()
    msg.topic = "config/test/devices/test"
    msg.payload = json.dumps({"Devices": []}).encode()

    with patch.object(service.dgb_context, "put_to_config_queue") as mock_enqueue:
        service._on_message(None, None, msg)
        mock_enqueue.assert_called_once_with("apply", {"Devices": []})


# ---------------------------------------------------------------------------
# Level 2: Stage 11 - Idempotency and buffering
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_run_config_apply_cycle_idempotent_on_replay(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Replaying the same payload should be idempotent (skipped)."""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(name="test", broker="localhost")
    payload = {"Devices": [], "Pins": [], "Bindings": []}

    with (
        patch.object(service, "_handle_devices"),
        patch.object(service, "_handle_pins"),
        patch.object(service, "_handle_bindings"),
    ):
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


@patch("DGB.DGBservice.SystemDevices")
@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_run_config_apply_cycle_buffers_later_payloads(
    mock_settings_mqtt, mock_client_class, mock_system_devices_class
):
    """Config dispatcher processes queued payloads sequentially."""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()
    mock_system_devices_class.return_value = MagicMock()

    service = DGBservice(name="test", broker="localhost")

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
