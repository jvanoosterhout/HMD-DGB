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
from pydantic import ValidationError

from DGB.PinModels import PinModel

BASE_CONFIGS = {
    "in": {"pin": 17, "ptype": "in"},
    "out": {"pin": 27, "ptype": "out"},
    "count": {"pin": 5, "ptype": "count"},
    "nwayout": {"pin": 22, "ptype": "nwayout", "pin_list": [22, 23, 24]},
}


@pytest.mark.parametrize("ptype", BASE_CONFIGS)
@pytest.mark.parametrize("unique_id", ["pump", "garden_pump_pin_27", "pump-1", "0"])
def test_valid_unique_id_accepted(ptype, unique_id):
    config = PinModel(BASE_CONFIGS[ptype] | {"unique_id": unique_id})

    assert config.unique_id == unique_id


@pytest.mark.parametrize("ptype", BASE_CONFIGS)
def test_missing_unique_id_rejected(ptype):
    with pytest.raises(ValidationError, match="unique_id"):
        PinModel(BASE_CONFIGS[ptype])


@pytest.mark.parametrize("ptype", BASE_CONFIGS)
@pytest.mark.parametrize("unique_id", ["", "Pump", "garden pump", "pump/1", "pump#", 5])
def test_invalid_unique_id_rejected(ptype, unique_id):
    with pytest.raises(ValidationError):
        PinModel(BASE_CONFIGS[ptype] | {"unique_id": unique_id})


def test_nwayout_pin_must_be_in_pin_list():
    with pytest.raises(ValidationError, match="must also be listed in pin_list"):
        PinModel(
            {"pin": 22, "unique_id": "motor", "ptype": "nwayout", "pin_list": [23, 24]}
        )


def test_nwayout_duplicate_gpio_in_pin_list_rejected():
    with pytest.raises(ValidationError, match="duplicate GPIO pins"):
        PinModel(
            {
                "pin": 22,
                "unique_id": "motor",
                "ptype": "nwayout",
                "pin_list": [22, 23, 23],
            }
        )


def test_nwayout_repeated_dummy_pins_allowed():
    config = PinModel(
        {"pin": 22, "unique_id": "motor", "ptype": "nwayout", "pin_list": [22, -1, -1]}
    )

    assert config.pin_list == [22, -1, -1]
