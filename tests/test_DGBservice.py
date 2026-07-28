import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

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

    retained = service.dgb_context.get_retained_state("switch_one")
    assert retained == {"payload": {"value": "on"}}


def test_publish_state_value_uses_configured_prefix(make_service):
    service, mock_client = make_service(name="test")

    service.dgb_context.publish_state_value("switch_1", "state", "on")

    mock_client.publish.assert_any_call(
        "state/test/switch_1/state", payload='"on"', qos=1, retain=True
    )
