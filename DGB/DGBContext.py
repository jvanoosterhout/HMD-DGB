from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Set, Literal


BinderCmd = Literal["post", "ruleset", "shutdown"]


@dataclass(frozen=True)
class BinderMessage:
    cmd: BinderCmd
    payload: Dict[str, Any]


FunctionMap = Dict[str, Callable[..., Any]]


class DGBContext:
    """
    Shared runtime context for DGB, containing:
    - device and GPIO pin registries (objects + callable functions)
    - bindings between devices and rulesets
    - message queue for binder/engine interaction
    - (optional) engine lock used by the durable_rules engine
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"{__name__}.DGBContext")

        self._devices_objects: Dict[str, Any] = {}
        self._devices_functions: Dict[str, FunctionMap] = {}

        self._pins_objects: Dict[str, Any] = {}
        self._pins_functions: Dict[str, FunctionMap] = {}

        # Bindings should be unique: device_id -> set(ruleset_name)
        self._bindings: Dict[str, Set[str]] = {}

        self.binder_queue: "queue.Queue[BinderMessage]" = queue.Queue()
        self.engine_lock: threading.Lock = threading.Lock()

        self._closed = False
        self._logger.info("DGBContext initialized.")

    def close(self) -> None:
        """Explicitly close context resources and signal shutdown."""
        if self._closed:
            return
        self._closed = True
        self.put_to_binder_queue("shutdown", {})
        self._logger.info("DGBContext closed (shutdown enqueued).")

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def add_device(
        self,
        unique_id: str,
        device_obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self._devices_objects[unique_id] = device_obj
        self._devices_functions[unique_id] = functions if functions else {}
        self._logger.info(
            "Added device %s with functions %s",
            unique_id,
            sorted(self._devices_functions[unique_id].keys()),
        )

    def add_pin(
        self,
        unique_id: str,
        pin_obj: Any,
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self._pins_objects[unique_id] = pin_obj
        self._pins_functions[unique_id] = functions if functions else {}
        self._logger.info(
            "Added pin %s with functions %s",
            unique_id,
            sorted(self._pins_functions[unique_id].keys()),
        )

    @staticmethod
    def _normalize_ruleset_name(ruleset_name: str) -> str:
        # strip suffix after '$' (as in your original code)
        return ruleset_name.split("$", 1)[0]

    def add_binding(self, device_id: str, ruleset_name: str) -> None:
        normalized = self._normalize_ruleset_name(ruleset_name)
        rulesets = self._bindings.setdefault(device_id, set())

        if normalized in rulesets:
            self._logger.info(
                "Device %s already had binding to ruleset %s", device_id, normalized
            )
            return

        rulesets.add(normalized)
        self._logger.info(
            "Added binding for device %s to ruleset %s", device_id, normalized
        )

    def get_bindings(self, device_id: str) -> Set[str]:
        # return a copy to prevent external mutation
        return set(self._bindings.get(device_id, set()))

    def get_device(self, unique_id: str) -> Any:
        return self._devices_objects.get(unique_id)

    def get_pin(self, unique_id: str) -> Any:
        return self._pins_objects.get(unique_id)

    def get_functions(self, unique_id: str) -> FunctionMap:
        if unique_id in self._devices_functions:
            return self._devices_functions[unique_id]
        if unique_id in self._pins_functions:
            return self._pins_functions[unique_id]
        return {}

    def put_to_binder_queue(self, cmd: BinderCmd, payload: Dict[str, Any]) -> None:
        if self._closed and cmd != "shutdown":
            raise RuntimeError("DGBContext is closed; no further commands allowed.")
        self.binder_queue.put(BinderMessage(cmd=cmd, payload=payload))
