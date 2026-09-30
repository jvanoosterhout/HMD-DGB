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
#
#    Structural validation for the config/{name}/devices/ overlay payload.
#    Validates shape only; component/pin-specific fields are still validated
#    by DeviceKeeper, PinModel, and Binder at RuntimePhase.CREATE.

from __future__ import annotations

from typing import Any

from DGB.SetStateResolver import CallArgumentResolver

_state_resolver = CallArgumentResolver()


def validate_config_payload(payload: dict[str, Any]) -> None:
    """Validate the structural shape of a config/{name}/devices/ payload.

    Args:
        payload: Decoded configuration payload.

    Raises:
        TypeError: When a section has the wrong type.
        ValueError: When a section is missing required fields.
    """
    if not isinstance(payload, dict):
        raise TypeError("config payload must be a dict")

    _validate_devices(payload.get("Devices", []))
    _validate_pins(payload.get("Pins", []))
    _validate_bindings(payload.get("Bindings", []))
    if "state_initialization" in payload:
        _validate_state_initialization(payload["state_initialization"])


def _validate_devices(devices: Any) -> None:
    if not isinstance(devices, list):
        raise TypeError("Devices must be a list")
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            raise TypeError(f"Devices[{index}] must be a dict")
        if "EntityInfo" not in device:
            raise ValueError(f"Devices[{index}] must contain 'EntityInfo'")
        entity_info = device["EntityInfo"]
        if not isinstance(entity_info, dict):
            raise TypeError(f"Devices[{index}].EntityInfo must be a dict")
        _require_non_empty_str(entity_info, "component", f"Devices[{index}].EntityInfo")
        _require_non_empty_str(entity_info, "unique_id", f"Devices[{index}].EntityInfo")


def _validate_pins(pins: Any) -> None:
    if not isinstance(pins, list):
        raise TypeError("Pins must be a list")
    for index, pin in enumerate(pins):
        if not isinstance(pin, dict):
            raise TypeError(f"Pins[{index}] must be a dict")
        if "PinInfo" not in pin:
            raise ValueError(f"Pins[{index}] must contain 'PinInfo'")
        pin_info = pin["PinInfo"]
        if not isinstance(pin_info, dict):
            raise TypeError(f"Pins[{index}].PinInfo must be a dict")
        if "pin" not in pin_info:
            raise ValueError(f"Pins[{index}].PinInfo must contain 'pin'")
        _require_non_empty_str(pin_info, "ptype", f"Pins[{index}].PinInfo")


def _validate_bindings(bindings: Any) -> None:
    if not isinstance(bindings, list):
        raise TypeError("Bindings must be a list")
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise TypeError(f"Bindings[{index}] must be a dict")
        if "BindInfo" not in binding:
            raise ValueError(f"Bindings[{index}] must contain 'BindInfo'")
        bind_info = binding["BindInfo"]
        if not isinstance(bind_info, dict) or not bind_info:
            raise TypeError(f"Bindings[{index}].BindInfo must be a non-empty dict")


def _validate_state_initialization(state_initialization: Any) -> None:
    if not isinstance(state_initialization, dict):
        raise TypeError("state_initialization must be a dict")

    for index, entry in enumerate(_as_list(state_initialization.get("preset_action"))):
        prefix = f"state_initialization.preset_action[{index}]"
        if not isinstance(entry, dict):
            raise TypeError(f"{prefix} must be a dict")
        _require_non_empty_str(entry, "unique_id", prefix)
        if entry.get("call") != "set_state":
            raise ValueError(f"{prefix}.call must be 'set_state'")
        _state_resolver.normalize_argument_definitions(entry.get("args"))

    for index, entry in enumerate(_as_list(state_initialization.get("persist_action"))):
        prefix = f"state_initialization.persist_action[{index}]"
        if not isinstance(entry, dict):
            raise TypeError(f"{prefix} must be a dict")
        _require_non_empty_str(entry, "unique_id", prefix)
        call_names = entry.get("call")
        if not isinstance(call_names, list) or not call_names:
            raise ValueError(f"{prefix}.call must be a non-empty list")
        if not all(isinstance(name, str) and name.strip() for name in call_names):
            raise ValueError(f"{prefix}.call must contain non-empty strings")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    raise TypeError("Expected a dict, a list, or None")


def _require_non_empty_str(source: dict[str, Any], key: str, prefix: str) -> None:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}.{key} must be a non-empty str")
