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
#    Startup-state initialization helpers for DGBservice (stages 3/5/6).

from __future__ import annotations

import json
import logging
from typing import Any

from DGB.ActionArguments import ArgumentBuilder
from DGB.DGBContext import DGBContext
from DGB.StartupPolicy import SourceDecision


class StartupStateInitializer:
    def __init__(
        self,
        dgb_context: DGBContext,
        mqtt_client: Any,
        logger: logging.Logger,
        arg_builder: ArgumentBuilder,
        state_shadow_prefix: str,
    ) -> None:
        self.dgb_context = dgb_context
        self.mqtt_client = mqtt_client
        self.logger = logger
        self.arg_builder = arg_builder
        self.state_shadow_prefix = state_shadow_prefix

    def is_state_shadow_topic(self, topic: str) -> bool:
        return topic.startswith(self.state_shadow_prefix)

    def _state_shadow_topic(self, unique_id: str) -> str:
        return f"{self.state_shadow_prefix}{unique_id}"

    def _unique_id_from_state_shadow_topic(self, topic: str) -> str | None:
        if not topic.startswith(self.state_shadow_prefix):
            return None
        unique_id = topic[len(self.state_shadow_prefix) :]
        return unique_id if unique_id else None

    def _decode_shadow_payload(self, payload: bytes) -> Any:
        raw = payload.decode()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def handle_state_shadow_message(self, msg) -> None:
        unique_id = self._unique_id_from_state_shadow_topic(msg.topic)
        if unique_id is None:
            self.logger.warning("Ignoring invalid state shadow topic: %s", msg.topic)
            return

        raw_payload = msg.payload.decode()
        decoded_payload = self._decode_shadow_payload(msg.payload)
        self.dgb_context.record_retained_value(
            unique_id=unique_id,
            topic=msg.topic,
            payload_raw=raw_payload,
            payload_decoded=decoded_payload,
        )
        self.logger.info(
            "Stored retained shadow value for %s from %s", unique_id, msg.topic
        )

    def register_retained_subscriptions(
        self, decisions: dict[str, SourceDecision]
    ) -> None:
        for unique_id, decision in decisions.items():
            if decision.source != "retain_state":
                continue
            topic = self._state_shadow_topic(unique_id)
            self.dgb_context.register_retained_interest(unique_id, topic)
            self.mqtt_client.subscribe(topic, qos=1)
            self.logger.info(
                "Subscribed to retained shadow topic for %s: %s", unique_id, topic
            )

    def resolve_retained_sources(self, decisions: dict[str, SourceDecision]) -> None:
        for unique_id, decision in decisions.items():
            if decision.source != "retain_state":
                continue

            retained = self.dgb_context.get_retained_value(unique_id)
            if retained is not None:
                self.logger.info(
                    "Startup source for %s resolved from retained shadow topic %s",
                    unique_id,
                    retained.topic,
                )
                continue

            if decision.fallback == "preset_value":
                self.logger.info(
                    "Startup source for %s retained missing; falling back to preset_value=%r",
                    unique_id,
                    decision.fallback_value,
                )
            else:
                self.logger.info(
                    "Startup source for %s retained missing; falling back to no_state",
                    unique_id,
                )

    def apply_configured_defaults(self, decisions: dict[str, SourceDecision]) -> None:
        for unique_id, decision in decisions.items():
            if decision.source != "preset_value":
                continue

            functions = self.dgb_context.get_functions(unique_id)
            if not functions:
                self.logger.warning(
                    "Configured default for %s ignored: no registered functions",
                    unique_id,
                )
                continue

            try:
                resolved = self.arg_builder.resolve_callable_action(
                    action_payload={"unique_id": unique_id, **decision.value},
                    function_resolver=lambda uid, call: functions.get(call),
                    source_label="preset_value",
                    allow_context_refs=False,
                )
            except (ValueError, KeyError) as e:
                self.logger.warning(
                    "Configured default for %s ignored: %s",
                    unique_id,
                    str(e),
                )
                continue

            call_args = self.arg_builder.build_call_args(resolved.arg_defs, {})
            resolved.action_fn(**call_args)
            self.logger.info(
                "Applied configured default via action call for %s (%s)",
                resolved.unique_id,
                resolved.call_name,
            )
