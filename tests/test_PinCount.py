from unittest.mock import MagicMock, patch

import pytest

from DGB.PinCount import Pin_count
from DGB.PinModels import PinModel


def test_pincount_model_defaults_enable_both_edges():
    config = PinModel({"pin": 5, "ptype": "count"})

    assert config.when_activated is True
    assert config.when_deactivated is True
    assert config.scaling_factor == 1.0


def test_pincount_model_accepts_edge_options():
    config = PinModel(
        {
            "pin": 5,
            "ptype": "count",
            "when_activated": True,
            "when_deactivated": False,
            "scaling_factor": 10.0,
        }
    )

    assert config.when_activated is True
    assert config.when_deactivated is False
    assert config.scaling_factor == 10.0


def test_pincount_model_rejects_non_positive_scaling_factor():
    with pytest.raises(ValueError, match="scaling_factor"):
        PinModel({"pin": 5, "ptype": "count", "scaling_factor": 0})


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
            "scaling_factor": 1.0,
        }
    )
    dgb_context = MagicMock()

    pin = Pin_count(config=config, dgb_context=dgb_context)
    pin.calback = MagicMock()

    pin.ConfigurePin()

    assert pin_device.when_activated is pin.calback
    assert pin_device.when_deactivated is None
    pin.calback.assert_called_once()


def test_pincount_callback_posts_scaled_total():
    config = PinModel(
        {
            "pin": 5,
            "ptype": "count",
            "scaling_factor": 10.0,
            "when_activated": False,
            "when_deactivated": False,
        }
    )
    dgb_context = MagicMock()

    pin = Pin_count(config=config, dgb_context=dgb_context)
    pin.calback()

    dgb_context.put_to_binder_queue.assert_called_once_with(
        "post", {"unique_id": "5", "payload": 0.1}
    )


def test_pincount_set_state_restores_scaled_total():
    config = PinModel(
        {
            "pin": 5,
            "ptype": "count",
            "scaling_factor": 10.0,
            "when_activated": False,
            "when_deactivated": False,
        }
    )
    dgb_context = MagicMock()

    pin = Pin_count(config=config, dgb_context=dgb_context)

    assert pin.set_state("scaled_total", 1.5) is True
    assert pin.count_total == 15
