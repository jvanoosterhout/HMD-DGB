import json
import os
import queue
import threading
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from DGB.DGBservice import DGBservice


def test_service_startup_smoke():
    with (
        patch("DGB.DGBservice.SystemDevices") as mock_system_devices,
        patch("DGB.DGBservice.mqtt.Client") as mock_client_class,
        patch("DGB.DGBservice.Settings.MQTT"),
        patch("DGB.DGBservice.Binder.start_event_dispatcher"),
    ):
        client = MagicMock()
        mock_client_class.return_value = client
        mock_system_devices.return_value = MagicMock()

        service = DGBservice(
            name="startup-smoke",
            broker="localhost",
            username="",
            password="",
            location="CI",
        )

    service.handle_temp_subscription = MagicMock()
    try:
        service.start()

        assert service.config_thread.is_alive()
        assert service.sensor_thread.is_alive()
        client.loop_start.assert_called_once()
    finally:
        service.stop()
        if service.config_thread.is_alive():
            service.config_thread.join(timeout=5)
        if service.sensor_thread.is_alive():
            service.sensor_thread.join(timeout=5)

    assert not service.config_thread.is_alive()
    assert not service.sensor_thread.is_alive()


@pytest.fixture
def running_real_mqtt_service():
    if os.getenv("DGB_CI_MQTT_SMOKE") != "1":
        pytest.skip("real MQTT smoke tests run only in the dedicated CI job")

    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory
    from paho.mqtt import client as mqtt

    broker_host = os.getenv("DGB_CI_MQTT_HOST", "127.0.0.1")
    broker_port = int(os.getenv("DGB_CI_MQTT_PORT", "1883"))
    name = f"ci-smoke-{uuid.uuid4().hex[:12]}"
    subscribed = threading.Event()
    discovery_messages = queue.Queue()
    observer = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"observer-{name}",
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            return
        client.subscribe("homeassistant/sensor/#", qos=1)

    def on_subscribe(client, userdata, mid, reason_code_list, properties):
        subscribed.set()

    def on_message(client, userdata, message):
        discovery_messages.put((message.topic, message.payload))

    observer.on_connect = on_connect
    observer.on_subscribe = on_subscribe
    observer.on_message = on_message

    observer.connect(broker_host, broker_port, keepalive=15)
    observer.loop_start()
    service = None
    previous_pin_factory = Device.pin_factory
    Device.pin_factory = MockFactory()
    sensor_updates = patch("DGB.SystemDevices.SystemDevices.update_sensor_values")
    sensor_updates.start()

    try:
        assert subscribed.wait(timeout=10), "observer did not subscribe"
        with (
            patch(
                "DGB.SystemDevices.SystemDevices._get_latest_release_tag",
                return_value="unknown",
            ),
            patch(
                "DGB.SystemDevices.SystemDevices._get_ip",
                return_value="localhost",
            ),
        ):
            service = DGBservice(
                name=name,
                broker=broker_host,
                port=broker_port,
                username="",
                password="",
                location="CI",
                system_sensor_update_rate=60,
            )
        service.start()
        yield service, observer, discovery_messages
    finally:
        if service is not None:
            service.stop()
            if service.config_thread.is_alive():
                service.config_thread.join(timeout=5)
            if service.sensor_thread.is_alive():
                service.sensor_thread.join(timeout=5)
        sensor_updates.stop()
        observer.loop_stop()
        observer.disconnect()
        Device.pin_factory = previous_pin_factory


def wait_for_sensor_discovery(discovery_messages, unique_id, timeout=10):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"sensor discovery for {unique_id!r} was not published"
            )
        try:
            topic, payload = discovery_messages.get(timeout=remaining)
        except queue.Empty as exc:
            raise AssertionError(
                f"sensor discovery for {unique_id!r} was not published"
            ) from exc

        configuration = json.loads(payload)
        if configuration.get("unique_id") == unique_id:
            return topic, configuration


def test_real_mqtt_startup_publishes_service_sensor(running_real_mqtt_service):
    service, _, discovery_messages = running_real_mqtt_service
    unique_id = f"{service.name}_service_version"

    topic, configuration = wait_for_sensor_discovery(discovery_messages, unique_id)

    assert topic.startswith("homeassistant/sensor/")
    assert configuration["name"] == "Current version"


def test_real_mqtt_configuration_publishes_sensor(running_real_mqtt_service):
    service, observer, discovery_messages = running_real_mqtt_service
    unique_id = f"{service.name}-configured-sensor"
    payload = json.dumps(
        {
            "Devices": [
                {
                    "EntityInfo": {
                        "component": "sensor",
                        "unique_id": unique_id,
                        "name": "CI configured sensor",
                    }
                }
            ],
            "Pins": [],
            "Bindings": [],
        }
    )
    published = observer.publish(service.config_topic, payload=payload, qos=1)
    published.wait_for_publish(timeout=10)

    topic, configuration = wait_for_sensor_discovery(discovery_messages, unique_id)

    assert topic.startswith("homeassistant/sensor/")
    assert configuration["name"] == "CI configured sensor"
