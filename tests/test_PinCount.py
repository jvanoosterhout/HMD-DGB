from unittest.mock import MagicMock, patch

from DGB.PinModels import PinModel
from DGB.PinCount import Pin_count


def test_pincount_model_defaults_enable_both_edges():
    config = PinModel({"pin": 5, "ptype": "count"})

    assert config.when_activated is True
    assert config.when_deactivated is True


def test_pincount_model_accepts_edge_options():
    config = PinModel(
        {
            "pin": 5,
            "ptype": "count",
            "when_activated": True,
            "when_deactivated": False,
        }
    )

    assert config.when_activated is True
    assert config.when_deactivated is False


@patch("DGB.PinCount.DigitalInputDevice")
def test_pincount_configure_pin_uses_edge_options(mock_input_device):
    pin_device = MagicMock()
    mock_input_device.return_value = pin_device

    config = PinModel(
        {
            "pin": 5,
            "ptype": "count",
            "pull_up": False,
            "when_activated": True,
            "when_deactivated": False,
        }
    )
    dgb_context = MagicMock()

    pin = Pin_count(config=config, dgb_context=dgb_context)
    pin.calback = MagicMock()

    pin.ConfigurePin()

    assert pin_device.when_activated is pin.calback
    assert pin_device.when_deactivated is None
    pin.calback.assert_called_once()
