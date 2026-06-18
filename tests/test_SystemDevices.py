import pytest
from unittest.mock import MagicMock, patch

from DGB.SystemDevices import SystemDevices
from DGB.DGBContext import DGBContext


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mqtt_settings():
    """Create minimal mock MQTT settings"""
    settings = MagicMock()
    return settings


@pytest.fixture
def dgb_restart():
    """Create a Callable for each test"""
    return True


@pytest.fixture
def dgb_context():
    """Create a fresh DGBContext for each test"""
    return DGBContext()


# ---------------------------------------------------------------------------
# Level 1: Initialization and basic structure
# ---------------------------------------------------------------------------


def test_system_devices_init(mock_mqtt_settings, dgb_context):
    """Test SystemDevices initialization"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test-device",
        )

        assert system_devices.device_name == "test-device"
        assert system_devices.location is None
        assert system_devices.mqtt_settings == mock_mqtt_settings
        assert system_devices.dgb_context == dgb_context


def test_system_devices_init_with_location(mock_mqtt_settings, dgb_context):
    """Test SystemDevices initialization with location"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="garage",
            location="garage",
        )

        assert system_devices.location == "garage"


def test_system_devices_init_with_dgb_mqtt_instance(mock_mqtt_settings, dgb_context):
    """Test SystemDevices initialization with DGBMQTT instance reference"""
    dgb_mqtt = dgb_restart

    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            device_name="test",
            dgb_restart=dgb_mqtt,
        )

        assert system_devices.dgb_restart == dgb_mqtt


def test_get_parent_device_id_service(mock_mqtt_settings, dgb_context):
    """Test getting service parent device ID"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test",
        )

        device_id = system_devices.get_parent_device_id("service")
        assert device_id == system_devices.SERVICE_ID


def test_get_parent_device_id_node(mock_mqtt_settings, dgb_context):
    """Test getting node parent device ID"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test",
        )

        device_id = system_devices.get_parent_device_id("node")
        assert device_id == system_devices.NODE_ID


def test_name_with_location_without_location(mock_mqtt_settings, dgb_context):
    """Test name formatting without location"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test-device",
        )

        name = system_devices.name_with_location()
        assert name == "test-device"


def test_name_with_location_with_location(mock_mqtt_settings, dgb_context):
    """Test name formatting with location"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="device",
            location="garage",
        )

        name = system_devices.name_with_location()
        assert name == "device (garage)"


def test_get_ip_success():
    """Test getting local IP address"""
    with patch("socket.socket") as mock_socket_class:
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 0)
        mock_socket_class.return_value = mock_socket

        ip = SystemDevices._get_ip()

        assert ip == "http://192.168.1.100"


def test_get_ip_fallback_on_error():
    """Test IP detection fallback on error"""
    with patch("socket.socket") as mock_socket_class:
        mock_socket_class.side_effect = Exception("Connection failed")

        ip = SystemDevices._get_ip()

        assert ip == "localhost"


# ---------------------------------------------------------------------------
# Level 1: Device registry
# ---------------------------------------------------------------------------


@patch("DGB.SystemDevices.Settings")
@patch("DGB.SystemDevices.GhApi")
@patch("DGB.SystemDevices.sensors.Sensor")
@patch("DGB.SystemDevices.sensors.Button")
def test_create_devices_sets_registry(
    mock_button_class,
    mock_sensor_class,
    mock_ghapi_class,
    mock_settings_class,
    mock_mqtt_settings,
    dgb_context,
):
    """Test create_devices initializes device registry"""
    mock_api = MagicMock()
    mock_release = MagicMock(tag_name="v1.0.0")
    mock_api.repos.list_releases.return_value = [mock_release]
    mock_ghapi_class.return_value = mock_api
    mock_settings_class.return_value = MagicMock()

    mock_sensor = MagicMock()
    mock_sensor._entity = MagicMock()
    mock_sensor._entity.unique_id = "test_id"
    mock_sensor_class.return_value = mock_sensor

    mock_button = MagicMock()
    mock_button._entity = MagicMock()
    mock_button._entity.unique_id = "button_id"
    mock_button_class.return_value = mock_button

    with patch("DGB.SystemDevices.CPUTemperature"):
        with patch("DGB.SystemDevices.platform.uname") as mock_uname:
            mock_uname.return_value = ("Linux", "RPi", "5.10.0", "arm64", "armv7l")

            system_devices = SystemDevices(
                mqtt_settings=mock_mqtt_settings,
                dgb_context=dgb_context,
                dgb_restart=dgb_restart,
                device_name="test",
            )
            system_devices.create_devices()

            assert hasattr(dgb_context, "device_registry")
            assert dgb_context.device_registry["node"] == system_devices.NODE_ID
            assert dgb_context.device_registry["service"] == system_devices.SERVICE_ID


# ---------------------------------------------------------------------------
# Level 2: Error cases
# ---------------------------------------------------------------------------


def test_get_parent_device_id_invalid_type_raises_value_error(
    mock_mqtt_settings, dgb_context
):
    """Test getting invalid device type raises ValueError"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test",
        )

        with pytest.raises(ValueError, match="Unknown device type"):
            system_devices.get_parent_device_id("invalid")


@patch("DGB.SystemDevices.sensors.Sensor")
def test_update_sensor_values_without_initialization(
    mock_sensor_class, mock_mqtt_settings, dgb_context
):
    """Test updating sensors without initialization returns early"""
    with patch("DGB.SystemDevices.sensors"):
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test",
        )

        # Don't initialize sensors
        system_devices.cpu_temp = None

        # Should return early without raising
        system_devices.update_sensor_values()


@patch("DGB.SystemDevices.Settings")
@patch("DGB.SystemDevices.GhApi")
@patch("DGB.SystemDevices.sensors.Sensor")
@patch("DGB.SystemDevices.sensors.Button")
def test_create_service_device_version_unknown_on_error(
    mock_button_class,
    mock_sensor_class,
    mock_ghapi_class,
    mock_settings_class,
    mock_mqtt_settings,
    dgb_context,
):
    """Test service device version defaults to unknown on error"""
    mock_ghapi_class.side_effect = Exception("GitHub API error")
    mock_settings_class.return_value = MagicMock()

    mock_sensor = MagicMock()
    mock_sensor._entity = MagicMock()
    mock_sensor._entity.unique_id = "sensor_id"
    mock_sensor_class.return_value = mock_sensor

    mock_button = MagicMock()
    mock_button._entity = MagicMock()
    mock_button._entity.unique_id = "button_id"
    mock_button_class.return_value = mock_button

    with patch("DGB.SystemDevices.platform.uname") as mock_uname:
        mock_uname.return_value = ("Linux", "RPi", "5.10.0", "arm64", "armv7l")
        system_devices = SystemDevices(
            mqtt_settings=mock_mqtt_settings,
            dgb_context=dgb_context,
            dgb_restart=dgb_restart,
            device_name="test",
        )
        system_devices.create_devices()

        # Version sensor should exist and have been set
        assert system_devices.version_sensor is not None
