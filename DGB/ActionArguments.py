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
#    Argument handling for dynamic function calls in actions.
#    Supports durable.lang context path resolution and type coercion.

from __future__ import annotations

import logging
from typing import Any, Callable, get_type_hints, get_origin, get_args, Union
import types
from dataclasses import dataclass


@dataclass
class ArgDefinition:
    """Represents a single argument to be passed to a function."""

    name: str
    value: Any
    is_context_ref: bool = False
    context_path: str | None = None  # e.g., "m.payload" or "first.payload"
    target_types: tuple[type, ...] = ()
    accepts_none: bool = False  # True if type is Optional or Union with None


class ArgumentBuilder:
    """
    Builds and coerces arguments for function calls from durable.lang context.

    Syntax:
    - Literal: {"name": "active_pin", "value": 5}
    - Context: {"name": "active_pin", "value": "$m.payload"}
    - Context: {"name": "active_pin", "value": "$first.payload"}
    """

    CONTEXT_REF_PREFIX = "$"

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ArgumentBuilder")

    @staticmethod
    def _extract_non_none_types(annotation: Any) -> tuple[tuple[type, ...], bool]:
        """
        Extract non-None types from a Union/Optional annotation.

        Examples:
        - int -> ((int,), False)
        - int | None -> ((int,), True)
        - Optional[str] -> ((str,), True)
        - str | int | None -> ((str, int), True)
        - None -> ((), True)
        - str | int -> ((str, int), False)

        Args:
            annotation: Type annotation (possibly Union/Optional)

        Returns:
            Tuple of (extracted_types, accepts_none)
        """
        # Handle None directly
        if annotation is None or annotation is type(None):
            return ((), True)

        # Get origin and args (works for Union, Optional, etc.)
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Not a Union/Optional - return as-is
        if origin not in (Union, types.UnionType):
            return ((annotation,), False)

        # Extract non-None types from Union
        non_none_types = [arg for arg in args if arg is not type(None)]
        accepts_none = len(non_none_types) < len(args)
        if non_none_types:
            return (tuple(non_none_types), accepts_none)
        else:
            return ((), True)

    def parse_argument_definitions(
        self,
        args_config: list[dict[str, Any]] | None,
        function: Callable,
    ) -> list[ArgDefinition]:
        """
        Parse argument definitions from config and match to function signature.

        Args:
            args_config: List of {"name": str, "value": Any or "$context.path"} dicts
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
            self.logger.debug(f"Could not get type hints for {function}: {e}")
            hints = {}

        arg_defs = []
        for arg_config in args_config:
            name = arg_config.get("name")
            value = arg_config.get("value")

            if not name:
                raise ValueError(f"Argument missing 'name' key: {arg_config}")
            if value is None:
                raise ValueError(f"Argument '{name}' missing 'value' key")

            # Check if this is a context reference
            is_context_ref = isinstance(value, str) and value.startswith(
                self.CONTEXT_REF_PREFIX
            )
            context_path = None

            if is_context_ref:
                context_path = value[len(self.CONTEXT_REF_PREFIX) :]

            # Get target type from function hints
            annotation = hints.get(name, None)
            target_types, accepts_none = self._extract_non_none_types(annotation)

            arg_def = ArgDefinition(
                name=name,
                value=value,
                is_context_ref=is_context_ref,
                context_path=context_path,
                target_types=target_types,
                accepts_none=accepts_none,
            )
            arg_defs.append(arg_def)

            self.logger.debug(
                f"Parsed arg '{name}': context_ref={is_context_ref}, "
                f"path={context_path}, target_types={target_types}"
            )

        return arg_defs

    def coerce_value(
        self,
        value: Any,
        target_types: tuple[type, ...] = (),
    ) -> Any:
        """
        Coerce a value to the target type.

        Supports:
        - str -> bool ("true"/"false", "1"/"0", "on"/"off", "yes"/"no" - case insensitive)
        - str -> int/float (via float() then int() if needed)
        - Any -> Any (identity if no target_types)
        - None passthrough

        Args:
            value: The value to coerce
            target_types: Candidate Python types in order (for Union annotations)

        Returns:
            Coerced value
        """
        # self.logger.info(f"Coercing value {value} to types {target_types}")
        if value is None:
            return value

        # If union candidates are provided, return value unchanged only when
        # current runtime type exactly matches one of those candidates.
        if target_types:
            value_type = type(value)
            for candidate_type in target_types:
                if value_type is candidate_type:
                    return value

        # Fallback target is the first candidate type.
        fallback_type = target_types[0] if target_types else None
        if fallback_type is None:
            return value

        # If already exact fallback type, return as-is
        if type(value) is fallback_type:
            return value

        # Handle bool (special case - many string representations)
        if fallback_type is bool:
            return self._coerce_to_bool(value)

        # Handle int
        if fallback_type is int:
            if isinstance(value, bool):
                return int(value)
            return int(self._coerce_to_float(value))

        # Handle float
        if fallback_type is float:
            return self._coerce_to_float(value)

        # Handle str
        if fallback_type is str:
            return str(value)

        # Handle bytes
        if fallback_type is bytes:
            if isinstance(value, str):
                return value.encode("utf-8")
            if isinstance(value, bytearray):
                return bytes(value)

        # Default: try direct conversion
        try:
            return fallback_type(value)
        except (TypeError, ValueError) as e:
            self.logger.error(
                f"Could not coerce {value!r} to {fallback_type}: {e}. Returning False."
            )
            return False

    @staticmethod
    def _coerce_to_float(value: Any) -> float:
        try:
            return float(value)
        except ValueError as e:
            print(f"ERROR!: Could not coerce {value!r} to float: {e}. Returning False.")
            return False

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
            # raise ValueError(f"Cannot convert {value!r} to bool")
        # raise ValueError(f"Cannot convert type {type(value).__name__} to bool")
        print(f"ERROR!: Could not coerce {value!r} to bool. Returning False.")
        return False

    def resolve_context_value(
        self,
        context_path: str,
        c: Any,
    ) -> Any:
        """
        Resolve a value from durable.lang context using dot notation.

        Examples:
        - "c.m.payload"        -> c.m['payload'] or c.m.payload
        - "c.first.c.payload"  -> c.first['payload'] or c.first.payload
        - "c.second.payload"   -> c.second.payload

        Args:
            context_path: Dot-separated path like "c.m.payload"
            c: Durable.lang context object

        Returns:
            Resolved value or None if path not found
        """
        parts = context_path.split(".")
        current = c

        for part in parts:
            if current is None:
                self.logger.warning(
                    f"Context path resolution stopped at None "
                    f"(remaining: {'.'.join(parts[parts.index(part) :])})"
                )
                return None

            # Handle sequence access. Durable "count" aggregations can provide
            # lists of matching events under c.m. For paths like "m.payload",
            # use the last event by default.
            if isinstance(current, (list, tuple)):
                if not current:
                    self.logger.warning(
                        "Context path resolution encountered an empty sequence"
                    )
                    return None

                if part.isdigit():
                    idx = int(part)
                    if idx >= len(current):
                        self.logger.warning(
                            f"Index '{idx}' out of range for sequence of length {len(current)}"
                        )
                        return None
                    current = current[idx]
                    continue

                current = current[-1]

            # Try dict-style access first (more common in durable.lang)
            if isinstance(current, dict):
                if part not in current:
                    self.logger.warning(
                        f"Key '{part}' not found in dict. "
                        f"Available keys: {list(current.keys())}"
                    )
                    return None
                current = current[part]
            else:
                # Fall back to attribute access
                if not hasattr(current, part):
                    self.logger.warning(
                        f"Attribute '{part}' not found on {type(current).__name__}. "
                        f"Available: {[x for x in dir(current) if not x.startswith('_')]}"
                    )
                    return None
                current = getattr(current, part)

        return current

    def build_call_args(
        self,
        arg_defs: list[ArgDefinition],
        c: Any,
    ) -> dict[str, Any]:
        """
        Build actual arguments by resolving context references and coercing types.

        Called within durable.lang action handler with full context `c`.

        Args:
            arg_defs: List of parsed argument definitions
            c: Durable.lang context object (contains c.m, c.first, etc.)

        Returns:
            Dict of {"arg_name": coerced_value}
        """
        call_args = {}

        for arg_def in arg_defs:
            if arg_def.is_context_ref:
                # Resolve from durable context
                self.logger.debug(
                    f"Resolving context ref for '{arg_def.name}': "
                    f"path='{arg_def.context_path}'"
                )
                value = self.resolve_context_value(arg_def.context_path, c)
            else:
                value = arg_def.value

            # Coerce to target type
            coerced = self.coerce_value(value, arg_def.target_types)
            call_args[arg_def.name] = coerced

            self.logger.debug(
                f"Arg '{arg_def.name}': "
                f"raw={value!r}, coerced={coerced!r}, types={arg_def.target_types}"
            )

        return call_args
