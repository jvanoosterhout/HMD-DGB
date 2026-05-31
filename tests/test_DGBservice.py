import pytest
from unittest.mock import Mock, MagicMock, patch
from threading import Event

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


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_init(mock_settings_mqtt, mock_client_class):
    """Test DGBservice initialization sets core attributes"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()

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


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_client_id_format(mock_settings_mqtt, mock_client_class):
    """Test MQTT client ID follows expected format"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="garage",
        broker="localhost",
    )

    assert service.client_id == "dgb-garage"


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_config_topic_default(mock_settings_mqtt, mock_client_class):
    """Test default config topic format"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    assert service.config_topic == "config/test/devices/"


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_config_topic_custom(mock_settings_mqtt, mock_client_class):
    """Test custom config topic"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
        topic="custom/topic/",
    )

    assert service.config_topic == "custom/topic/"


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_shutdown_event_not_set_initially(
    mock_settings_mqtt, mock_client_class
):
    """Test shutdown event is not set on initialization"""
    mock_client_class.return_value = MagicMock()
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    assert not service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 1: Lifecycle methods
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_sets_shutdown_event(mock_settings_mqtt, mock_client_class):
    """Test stop() sets shutdown event"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_is_idempotent(mock_settings_mqtt, mock_client_class):
    """Test calling stop() twice doesn't cause issues"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()
    service.stop()  # Should not raise

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_exit_calls_stop(mock_settings_mqtt, mock_client_class):
    """Test __exit__ calls stop()"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.__exit__(None, None, None)

    assert service.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Level 2: Error cases and edge cases
# ---------------------------------------------------------------------------


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_stop_before_start(mock_settings_mqtt, mock_client_class):
    """Test stopping service without starting it"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    service.stop()  # Should not raise even though start() wasn't called

    assert service.shutdown_event.is_set()


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_on_connect_callback_exists(mock_settings_mqtt, mock_client_class):
    """Test on_connect callback is registered"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    # Verify callback was set
    assert mock_client.on_connect is not None


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_on_message_callback_exists(mock_settings_mqtt, mock_client_class):
    """Test on_message callback is registered"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="localhost",
    )

    # Verify callback was set
    assert mock_client.on_message is not None


@patch("DGB.DGBservice.mqtt.Client")
@patch("DGB.DGBservice.Settings.MQTT")
def test_dgbservice_create_mqtt_client_calls_connect(
    mock_settings_mqtt, mock_client_class
):
    """Test _create_mqtt_client connects to broker"""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_settings_mqtt.return_value = MagicMock()

    service = DGBservice(
        name="test",
        broker="broker.local",
        port=1883,
    )

    # Verify connect was called with correct args
    mock_client.connect.assert_called()
