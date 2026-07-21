#
#    Copyright 2024-2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
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
#    Binder to manage actions to execute on specific triggers.

#    The triggers are assumed to originate from a device or pin, which holds the binder.
#    The binder keeps a list of actions (references to functions of the target device)
#    that will execute when a specific trigger/callback of the holding device fires.
#    This means that one device has multiple binders: one per trigger.


from __future__ import annotations

import logging
import threading
from collections.abc import Mapping, Sequence, Callable
from typing import Any

from durable.lang import post, get_host
from durable.engine import MessageNotHandledException, MessageObservedException

from DGB.DGBContext import DGBContext, BinderMessage, DuplicatePolicy
from DGB.ActionArguments import ArgumentBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iter_parents(tree, child_key, path=()):
    """
    Yield tuples (path, run_value) where path shows how to reach the dict
    containing `child_key`. Path elements are dict keys or list indices.
    """
    if isinstance(tree, Mapping):
        if child_key in tree:
            yield (path + (child_key,), tree)

        for k, v in tree.items():
            yield from iter_parents(v, child_key, path + (k,))

    elif isinstance(tree, Sequence) and not isinstance(tree, (str, bytes, bytearray)):
        for i, item in enumerate(tree):
            yield from iter_parents(item, child_key, path + (i,))


# ---------------------------------------------------------------------------
# Timer registry (instance-based, testable)
# ---------------------------------------------------------------------------


class TimerRegistry:
    def __init__(
        self,
        timer_factory: Callable[
            [float, Callable[[], None]], threading.Timer
        ] = threading.Timer,
    ):
        self._timer_factory = timer_factory
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self, timer_id: str, delay_seconds: float, callback: Callable[[], None]):
        self.cancel(timer_id)

        timer = self._timer_factory(delay_seconds, callback)
        with self._lock:
            self._timers[timer_id] = timer
        timer.start()

    def cancel(self, timer_id: str) -> bool:
        with self._lock:
            if timer_id in self._timers:
                self._timers[timer_id].cancel()
            else:
                return False
            self._timers.pop(timer_id, None)
            return True


# ---------------------------------------------------------------------------
# Binder
# ---------------------------------------------------------------------------


class Binder:
    def __init__(self, dgb_context: DGBContext):
        self.dgb_context = dgb_context
        self.timers = TimerRegistry()
        self.arg_builder = ArgumentBuilder()
        self.logger = logging.getLogger("Binder")

    # ------------------------------------------------------------------
    # Action building (dispatcher)
    # ------------------------------------------------------------------

    def build_action(
        self,
        ruleset_name: str,
        rule_name: str,
        action_def: dict[str, Any],
    ) -> Callable[[Any], None]:
        """
        Build a single executable action callable from config.

        Supported shapes:
          - {"log": {"msg": str}}
          - {"action": {"unique_id": str, "call": str}}
          - {"action": {"unique_id": str, "call": str, "args": [{"name": str, "value": Any}]}}
          - {"timer": {"name": str, "action": "start", "seconds": float}}
          - {"timer": {"name": str, "action": "cancel"}}
        """
        match action_def:
            case {"log": {"msg": msg}}:
                return self._build_log_action(rule_name, msg)

            case {"action": {"unique_id": dev, "call": call, **rest}}:
                args_config = rest.get("args", None)
                return self._build_device_action(rule_name, dev, call, args_config)

            case {"timer": {"name": name, "action": "start", "seconds": secs}}:
                return self._build_timer_start_action(
                    ruleset_name, rule_name, name, secs
                )

            case {"timer": {"name": name, "action": "cancel"}}:
                return self._build_timer_cancel_action(rule_name, name)

            case _:
                raise ValueError(
                    f"Unknown action definition in rule '{rule_name}': {action_def!r}"
                )

    # ------------------------------------------------------------------
    # Action builders (private)
    # ------------------------------------------------------------------

    def _build_log_action(self, rule_name: str, msg: Any) -> Callable[[Any], None]:
        if not isinstance(msg, str):
            raise ValueError(f"log.msg must be str (rule '{rule_name}')")

        self.logger.info("building log %s", msg)

        def _log(c, _msg=msg):
            self.logger.info(_msg)

        _log.__name__ = f"log__{rule_name}"
        return _log

    def _build_device_action(
        self,
        rule_name: str,
        unique_id: Any,
        call_name: Any,
        args_config: list[dict[str, Any]] | None = None,
    ) -> Callable[[Any], None]:
        """
        Build a device action with optional dynamic arguments.

        Args:
            rule_name: Name of the rule
            unique_id: Device/pin unique_id
            call_name: Function name to call
            args_config: Optional list of {"name": str, "value": Any or "$c.path_to_value"} argument definitions
        """
        resolved = self.arg_builder.resolve_callable_action(
            action_payload={
                "unique_id": unique_id,
                "call": call_name,
                "args": args_config,
            },
            function_resolver=lambda uid, call: self.dgb_context.get_functions(uid).get(
                call
            ),
            source_label="action",
            allow_context_refs=True,
        )
        unique_id = resolved.unique_id
        call_name = resolved.call_name
        action_fn = resolved.action_fn
        arg_defs = resolved.arg_defs

        self.logger.info(
            "building action for %s.%s with %d args",
            unique_id,
            call_name,
            len(arg_defs),
        )

        def _device_action(
            c,
            _fn=action_fn,
            _rule=rule_name,
            _call=call_name,
            _dev=unique_id,
            _arg_defs=arg_defs,
        ):
            self.logger.info(
                "rule '%s' fired with action '%s' on device '%s'",
                _rule,
                _call,
                _dev,
            )
            # Build call arguments from context and coerce types
            call_args = self.arg_builder.build_call_args(_arg_defs, c)

            self.logger.debug(f"Calling {_call} with args: {call_args}")

            # Call with resolved arguments
            result = _fn(**call_args)
            c.s.return_value = {"value": True if result is None else bool(result)}

        _device_action.__name__ = f"action__{rule_name}__{unique_id}__{call_name}"
        return _device_action

    def _build_timer_start_action(
        self,
        ruleset_name: str,
        rule_name: str,
        name: Any,
        secs: Any,
    ) -> Callable[[Any], None]:
        if not isinstance(name, str) or not name:
            raise ValueError(f"timer.name must be non-empty str (rule '{rule_name}')")
        if secs is None:
            raise ValueError(
                f"timer.seconds required (rule '{rule_name}', timer '{name}')"
            )

        delay = float(secs)
        self.logger.info("building timer %s, start", name)

        def _timer_start(
            c,
            _name=name,
            _delay=delay,
            _rule=rule_name,
            _ruleset=ruleset_name,
        ):
            self.logger.info("Timer %s started for: %s", _name, _rule)

            def callback():
                base_ruleset = _ruleset.split("$", 1)[0]
                self.dgb_context.put_to_binder_queue(
                    "post",
                    {"timeout": _name, "rulesetname": base_ruleset},
                )

            self.timers.start(_name, _delay, callback)

        _timer_start.__name__ = f"timer__{rule_name}__{name}__start"
        return _timer_start

    def _build_timer_cancel_action(
        self,
        rule_name: str,
        name: Any,
    ) -> Callable[[Any], None]:
        if not isinstance(name, str) or not name:
            raise ValueError(f"timer.name must be non-empty str (rule '{rule_name}')")

        self.logger.info("building timer %s, cancel", name)

        def _timer_cancel(c, _name=name, _rule=rule_name):
            self.logger.info("Timer %s canceled for: %s", _name, _rule)
            self.timers.cancel(_name)

        _timer_cancel.__name__ = f"timer__{rule_name}__{name}__cancel"
        return _timer_cancel

    # ------------------------------------------------------------------
    # Condition handler
    # ------------------------------------------------------------------

    def build_condition_handler(
        self,
        ruleset_name: str,
        rule_name: str,
        actions_def: list[dict[str, Any]],
    ) -> Callable[[Any], None]:
        actions = [self.build_action(ruleset_name, rule_name, a) for a in actions_def]

        def condition_handler(c):
            c.s.return_value = {"value": "pending"}
            for act in actions:
                try:
                    act(c)
                except Exception:
                    self.logger.exception(
                        "Error executing action '%s' in rule '%s'",
                        getattr(act, "__name__", act),
                        rule_name,
                    )
                    raise

        condition_handler.__name__ = f"handler__{rule_name}"
        return condition_handler

    # ------------------------------------------------------------------
    # Event dispatcher / binding
    # ------------------------------------------------------------------

    def start_event_dispatcher(self):
        t = threading.Thread(target=self.event_dispatcher, daemon=True)
        self.logger.info("Starting event dispatcher")
        t.start()

    def event_dispatcher(self):
        msg = BinderMessage("", {"", ""})
        while True:
            msg = self.dgb_context.binder_queue.get()

            if msg.cmd == "shutdown":
                self.logger.info("Dispatcher shutdown requested")
                break

            if msg.cmd == "post":
                self._handle_post(msg.payload)
                self.dgb_context.binder_queue.task_done()

            if msg.cmd == "ruleset":
                self.logger.info("Adding new binding ruleset")
                self.new_binding(msg.payload)

    def _handle_post(self, payload: dict):
        if "unique_id" not in payload and "rulesetname" not in payload:
            raise ValueError("post payload requires unique_id or rulesetname")

        if "unique_id" in payload:
            rulesets = self.dgb_context.get_bindings(payload["unique_id"])
            if not rulesets:
                self.logger.warning(
                    "no rulesets found (Yet) for device %s", payload["unique_id"]
                )
        else:
            rulesets = [payload["rulesetname"]]

        # Filter rulesets by their cycle status: only allow dispatch for live bindings
        allowed_rulesets = [
            rs for rs in rulesets if self.dgb_context.is_binding_dispatch_allowed(rs)
        ]

        if not allowed_rulesets:
            self.logger.info(
                "Suppressing post event: no bindings are live yet: %s", payload
            )
            return

        rulesets = allowed_rulesets

        try:
            with self.dgb_context.engine_lock:
                for ruleset in rulesets:
                    self.logger.info(
                        "Posting event to ruleset %s: %s", ruleset, payload
                    )
                    post(ruleset, payload)

        except MessageNotHandledException as e:
            self.logger.error("Unmatched event: %s", e.message)
        except MessageObservedException as e:
            self.logger.error("Event already observed: %s", e.message)
        except Exception as e:
            self.logger.error(f"Exception {e} for {set}")

    def new_binding(self, bind: dict, policy: DuplicatePolicy = DuplicatePolicy.SKIP):

        # Register bindings
        self.logger.info(f"building new binding {next(iter(bind))}")

        with self.dgb_context.engine_lock:
            if not self._handle_existing_binding(next(iter(bind)), policy):
                return

        for path, all_parent in iter_parents(bind, "all"):
            for _, id_parent in iter_parents(all_parent["all"], "unique_id"):
                uid = id_parent["unique_id"]
                if self.dgb_context.get_object(uid) is None:
                    raise KeyError(
                        f"Device '{uid}' not found in dgb_context for binding"
                    )
                self.dgb_context.add_binding(uid, path[0])

        # Build condition handlers
        for path, run_parent in iter_parents(bind, "run"):
            actions = (
                run_parent["run"]
                if isinstance(run_parent["run"], list)
                else [run_parent["run"]]
            )
            run_parent["run"] = self.build_condition_handler(path[0], path[1], actions)

        with self.dgb_context.engine_lock:
            self.logger.info(f"Adding binding {next(iter(bind))} to durable rules")
            get_host().set_rulesets(bind)

    def _handle_existing_binding(
        self,
        rule_name: str,
        policy: DuplicatePolicy,
    ) -> bool:
        """
        Check whether a binding already exists in durable_rules and apply policy.

        Returns:
            True  -> caller may proceed with adding the binding
            False -> caller must skip adding
        """
        host = get_host()

        existing = host._ruleset_directory.get(rule_name.split("$", 1)[0])
        if existing is None:
            return True

        if policy == DuplicatePolicy.SKIP:
            self.logger.warning(f"Binding '{rule_name}' already exists -- skipping")
            return False

        # if policy == DuplicatePolicy.REPLACE:
        #     self.logger.warning(
        #         f"Binding '{rule_name}' already exists -- replacing"
        #     )
        #     self._remove_ruleset_from_host(host, rule_name)
        #     return True

        self.logger.warning(
            f"Binding '{rule_name}' already exists -- unknown policy '{policy}', skipping"
        )
        return False

    # def _remove_ruleset_from_host(self, host, rule_name: str) -> None:
    #     """
    #     Remove a ruleset from durable host internals.

    #     Important:
    #     - remove from _ruleset_directory
    #     - remove the actual ruleset object from _ruleset_list
    #     """
    #     ruleset = host._ruleset_directory.pop(rule_name, None)
    #     if ruleset is None:
    #         return

    #     try:
    #         host._ruleset_list.remove(ruleset)
    #     except ValueError:
    #         self.logger.warning(
    #             f"Ruleset '{rule_name}' was removed from _ruleset_directory "
    #             f"but not found in _ruleset_list"
    #         )
