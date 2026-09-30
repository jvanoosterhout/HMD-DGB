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

from DGB.ConfigSchema import validate_config_payload


def test_empty_payload_is_valid():
    """A payload without any section is valid."""
    validate_config_payload({})


def test_valid_full_payload_passes():
    """A payload with all sections populated passes validation."""
    validate_config_payload(
        {
            "Devices": [{"EntityInfo": {"component": "switch", "unique_id": "s1"}}],
            "Pins": [{"PinInfo": {"pin": 17, "ptype": "in"}}],
            "Bindings": [{"BindInfo": {"rs1": {}}}],
            "state_initialization": {
                "preset_action": [
                    {
                        "unique_id": "s1",
                        "call": "set_state",
                        "args": [{"name": "state", "value": "off"}],
                    }
                ],
                "persist_action": [{"unique_id": "s1", "call": ["set_state"]}],
            },
        }
    )


def test_payload_must_be_dict():
    with pytest.raises(TypeError, match="dict"):
        validate_config_payload([])


@pytest.mark.parametrize(
    "devices",
    [
        "not-a-list",
        [{"NoEntityInfo": {}}],
        [{"EntityInfo": "not-a-dict"}],
        [{"EntityInfo": {"unique_id": "s1"}}],
        [{"EntityInfo": {"component": "switch"}}],
        [{"EntityInfo": {"component": "", "unique_id": "s1"}}],
    ],
)
def test_invalid_devices_rejected(devices):
    with pytest.raises((TypeError, ValueError)):
        validate_config_payload({"Devices": devices})


@pytest.mark.parametrize(
    "pins",
    [
        "not-a-list",
        [{"NoPinInfo": {}}],
        [{"PinInfo": "not-a-dict"}],
        [{"PinInfo": {"ptype": "in"}}],
        [{"PinInfo": {"pin": 17}}],
    ],
)
def test_invalid_pins_rejected(pins):
    with pytest.raises((TypeError, ValueError)):
        validate_config_payload({"Pins": pins})


@pytest.mark.parametrize(
    "bindings",
    [
        "not-a-list",
        [{"NoBindInfo": {}}],
        [{"BindInfo": "not-a-dict"}],
        [{"BindInfo": {}}],
    ],
)
def test_invalid_bindings_rejected(bindings):
    with pytest.raises((TypeError, ValueError)):
        validate_config_payload({"Bindings": bindings})


@pytest.mark.parametrize(
    "state_initialization",
    [
        "not-a-dict",
        {"preset_action": [{"call": "set_state", "args": []}]},
        {"preset_action": [{"unique_id": "s1", "call": "turn_on", "args": []}]},
        {
            "preset_action": [
                {"unique_id": "s1", "call": "set_state", "args": [{"bad": "shape"}]}
            ]
        },
        {"persist_action": [{"unique_id": "s1"}]},
        {"persist_action": [{"unique_id": "s1", "call": []}]},
        {"persist_action": [{"unique_id": "s1", "call": [""]}]},
    ],
)
def test_invalid_state_initialization_rejected(state_initialization):
    with pytest.raises((TypeError, ValueError)):
        validate_config_payload({"state_initialization": state_initialization})
