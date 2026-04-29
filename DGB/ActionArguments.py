#!/usr/bin/env python
# encoding: utf-8
"""
Argument handling for dynamic function calls in actions.
Supports type coercion and payload references.

Jeroen van Oosterhout, 28-04-2026
"""

from __future__ import annotations

import logging
from typing import Any, Callable, get_type_hints
from dataclasses import dataclass
from pydantic import BaseModel, Field, field_validator


@dataclass
class ArgDefinition:
    """Represents a single argument to be passed to a function."""

    name: str
    value: Any
    is_payload_ref: bool = False
    payload_key: str | None = None
    target_type: type | None = None


class ActionArgumentSchema(BaseModel):
    """Schema for action arguments in JSON config."""

    args: list[dict[str, Any]] | None = Field(
        default=None, description="List of arguments to pass to the function"
    )

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, v):
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("args must be a list")
        for i, arg in enumerate(v):
            if not isinstance(arg, dict):
                raise ValueError(f"arg {i} must be a dict with 'name' and 'value' keys")
            if "name" not in arg:
                raise ValueError(f"arg {i} missing 'name' key")
            if "value" not in arg:
                raise ValueError(f"arg {i} missing 'value' key")
        return v


class ArgumentBuilder:
    """Builds and coerces arguments for function calls."""

    PAYLOAD_REF_PREFIX = "$payload:"

    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.ArgumentBuilder")

    def parse_argument_definitions(
        self,
        args_config: list[dict[str, Any]] | None,
        function: Callable,
    ) -> list[ArgDefinition]:
        """
        Parse argument definitions from config and match to function signature.

        Args:
            args_config: List of {"name": str, "value": Any} dicts
            function: The target function to get type hints from

        Returns:
            List of ArgDefinition objects
        """
        if not args_config:
            return []

        # Get function signature type hints
        try:
            hints = get_type_hints(function)
        except Exception as e:
            self._logger.warning(f"Could not get type hints for {function}: {e}")
            hints = {}

        arg_defs = []
        for arg_config in args_config:
            name = arg_config["name"]
            value = arg_config["value"]

            # Check if this is a payload reference
            is_payload_ref = isinstance(value, str) and value.startswith(
                self.PAYLOAD_REF_PREFIX
            )
            payload_key = None

            if is_payload_ref:
                payload_key = value[len(self.PAYLOAD_REF_PREFIX) :]

            # Get target type from function hints
            target_type = hints.get(name, None)

            arg_def = ArgDefinition(
                name=name,
                value=value,
                is_payload_ref=is_payload_ref,
                payload_key=payload_key,
                target_type=target_type,
            )
            arg_defs.append(arg_def)

            self._logger.debug(
                f"Parsed arg '{name}': payload_ref={is_payload_ref}, "
                f"target_type={target_type}"
            )

        return arg_defs

    def coerce_value(
        self,
        value: Any,
        target_type: type | None,
    ) -> Any:
        """
        Coerce a value to the target type.

        Supports:
        - str -> bool ("true"/"false", "1"/"0", "on"/"off" - case insensitive)
        - str -> int/float (via float() then int() if needed)
        - Any -> Any (identity if no target_type)

        Args:
            value: The value to coerce
            target_type: The target Python type

        Returns:
            Coerced value
        """
        if target_type is None or value is None:
            return value

        # If already correct type, return as-is
        if isinstance(value, target_type):
            return value

        # Handle bool (special case - many representations)
        if isinstance(target_type, bool):
            return self._coerce_to_bool(value)

        # Handle int
        if isinstance(target_type, int):
            return int(float(value))

        # Handle float
        if isinstance(target_type, float):
            return float(value)

        # Handle str
        if isinstance(target_type, str):
            return str(value)

        # Default: try direct conversion
        try:
            return target_type(value)
        except (TypeError, ValueError) as e:
            self._logger.warning(f"Could not coerce {value!r} to {target_type}: {e}")
            return value

    @staticmethod
    def _coerce_to_bool(value: Any) -> bool:
        """Coerce various representations to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            s = value.lower().strip()
            if s in ("true", "1", "yes", "on"):
                return True
            if s in ("false", "0", "no", "off"):
                return False
            raise ValueError(f"Cannot convert {value!r} to bool")
        raise ValueError(f"Cannot convert {type(value)} to bool")

    def build_call_args(
        self,
        arg_defs: list[ArgDefinition],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build actual arguments by resolving payload references and coercing types.

        Args:
            arg_defs: List of parsed argument definitions
            payload: Optional payload dict for resolving $payload: references

        Returns:
            Dict of {"arg_name": coerced_value}
        """
        call_args = {}
        payload = payload or {}

        for arg_def in arg_defs:
            if arg_def.is_payload_ref:
                # Resolve from payload
                if arg_def.payload_key not in payload:
                    self._logger.warning(
                        f"Payload key '{arg_def.payload_key}' not found in payload. "
                        f"Using None."
                    )
                    value = None
                else:
                    value = payload[arg_def.payload_key]
            else:
                value = arg_def.value

            # Coerce to target type
            coerced = self.coerce_value(value, arg_def.target_type)
            call_args[arg_def.name] = coerced

        return call_args
