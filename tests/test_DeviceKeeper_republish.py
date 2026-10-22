from unittest.mock import MagicMock

from ha_mqtt_discoverable import Settings, sensors
from paho.mqtt.client import MQTT_ERR_SUCCESS, Client

from DGB.DeviceKeeper import DeviceKeeper, republish_last_state
from DGB.DGBContext import DGBContext


def _mock_client():
    client = MagicMock(spec=Client)
    client.subscribe.return_value = (MQTT_ERR_SUCCESS, 1)
    return client


def _make_switch(client, unique_id="s1", retain=None):
    info_kwargs = {"name": unique_id, "unique_id": unique_id}
    if retain is not None:
        info_kwargs["retain"] = retain
    settings = Settings(
        mqtt=Settings.MQTT(client=client),
        entity=sensors.SwitchInfo(**info_kwargs),
    )
    return sensors.Switch(settings, lambda *_: None)


def test_republish_last_state_skips_without_state():
    client = _mock_client()
    switch = _make_switch(client)
    client.publish.reset_mock()

    assert republish_last_state(switch) is False
    client.publish.assert_not_called()


def test_republish_last_state_publishes_state_with_retain_flag():
    client = _mock_client()
    switch = _make_switch(client, retain=True)
    switch.on()
    client.publish.reset_mock()

    assert republish_last_state(switch) is True
    client.publish.assert_called_once_with(switch.state_topic, "ON", retain=True)


def test_republish_entities_writes_config_and_state_for_all_entities():
    client = _mock_client()
    ctx = DGBContext()
    s1 = _make_switch(client, "s1")
    s2 = _make_switch(client, "s2")
    s1.off()
    ctx.add_object("s1", s1)
    ctx.add_object("s2", s2)
    ctx.add_object("pin1", object())  # non-HA objects are ignored
    client.publish.reset_mock()

    DeviceKeeper(None, ctx).republish_entities()

    topics = [c.args[0] for c in client.publish.call_args_list]
    assert s1.config_topic in topics
    assert s2.config_topic in topics
    assert s1.state_topic in topics
    assert s2.state_topic not in topics  # no known state yet
