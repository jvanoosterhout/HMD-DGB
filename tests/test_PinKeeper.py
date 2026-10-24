#
#    Copyright 2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from DGB.DGBContext import DGBContext
from DGB.PinKeeper import PinKeeper
from DGB.PinModels import PinModel
from DGB.PinNWayOut import Pin_N_way_out
from DGB.PinOut import Pin_out


@pytest.fixture(autouse=True)
def mock_pin_factory():
    previous = Device.pin_factory
    Device.pin_factory = MockFactory()
    yield
    Device.pin_factory.reset()
    Device.pin_factory = previous


@pytest.fixture
def dgb_context():
    return DGBContext()


@pytest.fixture
def pinkeeper(dgb_context):
    return PinKeeper(dgb_context=dgb_context)


def out_config(unique_id="relay_pin_20", pin=20, **extra):
    return PinModel({"pin": pin, "unique_id": unique_id, "ptype": "out"} | extra)


def nwayout_config(unique_id="motor_pin_22", pin_list=(22, 23, -1)):
    return PinModel(
        {
            "pin": pin_list[0],
            "unique_id": unique_id,
            "ptype": "nwayout",
            "pin_list": list(pin_list),
            "pin_names": ["open", "close", "stop"],
        }
    )


def test_pin_registered_under_unique_id(pinkeeper, dgb_context):
    assert pinkeeper.SetPin(out_config()) is True

    assert isinstance(dgb_context.get_object("relay_pin_20").dgb_obj, Pin_out)
    assert dgb_context.get_object("20") is None
    assert set(dgb_context.get_operations("relay_pin_20")) == {
        "on",
        "off",
        "blink",
        "set_state",
    }


def test_pin_starts_off(pinkeeper, dgb_context):
    pinkeeper.SetPin(out_config())

    assert dgb_context.get_object("relay_pin_20").dgb_obj.pin_device.value == 0


def test_existing_unique_id_skipped(pinkeeper, dgb_context):
    assert pinkeeper.SetPin(out_config()) is True
    assert pinkeeper.SetPin(out_config(pin=21)) is False

    assert dgb_context.get_object("relay_pin_20").dgb_obj.config.pin == 20


def test_unique_id_of_device_skipped(pinkeeper, dgb_context):
    dgb_context.add_object("relay_pin_20", object())

    assert pinkeeper.SetPin(out_config()) is False


def test_retained_action_placeholder_accepted(pinkeeper, dgb_context):
    dgb_context.record_retained_action(
        "relay_pin_20", "set_state", {"args": [{"name": "state", "value": "on"}]}
    )

    assert pinkeeper.SetPin(out_config()) is True
    dgb_object = dgb_context.get_object("relay_pin_20")
    assert isinstance(dgb_object.dgb_obj, Pin_out)
    assert "set_state" in dgb_object.retained_actions


def test_gpio_in_use_skipped(pinkeeper, dgb_context):
    assert pinkeeper.SetPin(out_config()) is True
    assert pinkeeper.SetPin(out_config(unique_id="other_relay")) is False

    assert dgb_context.get_object("other_relay") is None


def test_gpio_in_use_by_nwayout_pin_list(pinkeeper):
    assert pinkeeper.SetPin(nwayout_config()) is True

    assert pinkeeper._gpio_in_use(22) is True
    assert pinkeeper._gpio_in_use(23) is True
    assert pinkeeper._gpio_in_use(24) is False
    assert pinkeeper.SetPin(out_config(unique_id="relay_pin_23", pin=23)) is False


def test_nwayout_rejected_when_sub_gpio_in_use(pinkeeper, dgb_context):
    assert pinkeeper.SetPin(out_config(unique_id="relay_pin_23", pin=23)) is True

    assert pinkeeper.SetPin(nwayout_config()) is False
    assert dgb_context.get_object("motor_pin_22") is None


def test_nwayout_sub_pins_not_registered(pinkeeper, dgb_context):
    assert pinkeeper.SetPin(nwayout_config()) is True

    nwayout = dgb_context.get_object("motor_pin_22").dgb_obj
    assert isinstance(nwayout, Pin_N_way_out)
    assert [p.config.unique_id for p in nwayout.Pins] == ["motor_pin_22_1"]
    assert set(dgb_context.DGB_objects) == {"motor_pin_22"}
    assert set(dgb_context.get_operations("motor_pin_22")) == {
        "on",
        "off",
        "set_state",
    }


def test_nwayout_on_by_name_switches_sub_pin(pinkeeper, dgb_context):
    pinkeeper.SetPin(nwayout_config())
    nwayout = dgb_context.get_object("motor_pin_22").dgb_obj

    assert nwayout.on(active_pin="close") is True

    assert nwayout.active_pin == "close"
    assert nwayout.pin_device.value == 0
    assert nwayout.Pins[0].pin_device.value == 1


def test_del_closes_all_pins(pinkeeper, dgb_context):
    pinkeeper.SetPin(out_config())
    pinkeeper.SetPin(nwayout_config())
    relay = dgb_context.get_object("relay_pin_20").dgb_obj
    nwayout = dgb_context.get_object("motor_pin_22").dgb_obj

    pinkeeper.__del__()

    assert relay.pin_device.closed
    assert nwayout.pin_device.closed
    assert nwayout.Pins[0].pin_device.closed


def test_blink_without_duration_and_config_returns_false(pinkeeper, dgb_context):
    pinkeeper.SetPin(out_config())
    relay = dgb_context.get_object("relay_pin_20").dgb_obj

    assert relay.blink() is False


def test_blink_uses_configured_duration(pinkeeper, dgb_context):
    pinkeeper.SetPin(out_config(blink=2))
    relay = dgb_context.get_object("relay_pin_20").dgb_obj

    assert relay.blink() is True
