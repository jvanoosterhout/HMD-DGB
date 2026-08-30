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
# Resolves and coerces arguments for function calls and from durable.lang context with dot-notation paths.

from __future__ import annotations

import logging
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints


@dataclass
class ArgDefinition:
    """Single function argument with optional context reference and type coercion info."""

    name: str
    value: Any
    is_context_ref: bool = False
    context_path: str | None = None  # e.g., "m.payload" or "first.payload"
    target_types: tuple[type, ...] = ()
    accepts_none: bool = False  # True if type is Optional or Union with None


class SetStateResolver:
    """Parses, resolves, and coerces arguments for function calls from config and durable.lang context paths."""

    CONTEXT_REF_PREFIX = "$"

    def __init__(self) -> None:
        """Initialize resolver with logger."""
        self.logger = logging.getLogger(f"{__name__}.ArgumentBuilder")

    @staticmethod
    def _extract_non_none_types(annotation: Any) -> tuple[tuple[type, ...], bool]:
        """Extract non-None types from Union/Optional annotations.

        Args:
            annotation: Type annotation, potentially Union/Optional.

        Returns:
            (non_none_types, accepts_none) tuple.
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
    ) -> list[ArgDefinition] | None:
        """Parse argument configs and match to function signature via type hints.

        Args:
            args_config: List of {param_name: value_or_context_ref} dicts.
            function: Target function for type hint extraction.

        Returns:
            List of ArgDefinition objects.
        """
        if not args_config:
            return []

        # Get function signature type hints
        try:
            hints = get_type_hints(function)
        except (NameError, TypeError, AttributeError) as e:
            self.logger.debug(f"Could not get type hints for {function}: {e}")
            hints = {}

        arg_defs = []
        for arg_config in args_config:
            if not isinstance(arg_config, dict):
                raise TypeError(f"Argument config must be a dict: {arg_config!r}")
            if not arg_config:
                raise ValueError(
                    f"Argument config must contain at least one key-value pair: {arg_config}"
                )

            for name, value in arg_config.items():
                if not name:
                    raise ValueError(f"Argument has empty key: {arg_config}")

                # Check if this is a context reference
                is_context_ref = isinstance(value, str) and value.startswith(
                    self.CONTEXT_REF_PREFIX
                )
                context_path = None

                if is_context_ref:
                    context_path = value[len(self.CONTEXT_REF_PREFIX) :]

                # Get target type from function hints
                annotation = hints.get(name)
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
        """Coerce value to target type(s), supporting str/bool/int/float conversions.

        Args:
            value: Value to coerce.
            target_types: Candidate types from function hints.

        Returns:
            Coerced value.
        """
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
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError(
                f"Could not coerce {value!r} (type {type(value).__name__}) "
                f"to {fallback_type}"
            ) from e

    def _coerce_to_float(self, value: Any) -> float:
        """Convert value to float."""
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError(
                f"Could not coerce {value!r} (type {type(value).__name__}) to float"
            ) from e

    def _coerce_to_bool(self, value: Any) -> bool:
        """Coerce value to bool, supporting str representations and numeric types."""
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
        raise ValueError(
            f"Could not coerce {value!r} (type {type(value).__name__}) to bool. "
            f"Supported: bool, int, float, or str in {{'true', '1', 'yes', 'on', 'false', '0', 'no', 'off'}}"
        )

    def resolve_context_value(
        self,
        context_path: str,
        c: Any,
    ) -> Any:
        """Resolve value from confg or durable.lang context using dot notation path.

        Args:
            context_path: Dot-separated path (e.g., "m.payload").
            c: Durable.lang context object.

        Returns:
            Resolved value or None if path not found.
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
    ) -> dict[str, Any] | None:
        """Resolve config/context references and coerce all arguments for function call.

        Args:
            arg_defs: List of parsed argument definitions.
            c: Durable.lang context object.

        Returns:
            Dict of {param_name: coerced_value} ready to unpack as **kwargs.
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
