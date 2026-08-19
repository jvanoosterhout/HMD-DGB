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
#    Device keeper to manage home assistant device and entity configurations.

import logging
from functools import partial

from ha_mqtt_discoverable import Discoverable, EntityType, Settings, sensors
from paho.mqtt.client import Client, MQTTMessage

from DGB.DGBContext import DGBContext, DuplicatePolicy

# from DGB.Binder import post_event

logging.basicConfig(level="INFO")


class DeviceKeeper:
    def __init__(self, mqtt_settings: Settings.MQTT, dgb_context: DGBContext):
        self.entities = []
        self.mqtt_settings = mqtt_settings
        self.dgb_context = dgb_context
        self.logger = logging.getLogger("DeviceKeeper")
        self.logger.info("starting Entitykeeper")

    def new_device(self, dev, policy: DuplicatePolicy = DuplicatePolicy.SKIP):
        if "EntityInfo" in dev:
            if "component" in dev["EntityInfo"] and "unique_id" in dev["EntityInfo"]:
                self.logger.info(
                    "Creating {} entity '{}'".format(
                        dev["EntityInfo"]["component"], dev["EntityInfo"]["name"]
                    )
                )
                if not self._handle_existing_device(
                    dev["EntityInfo"]["unique_id"], policy
                ):
                    return

                # get direct_state_transition flag, if present
                dst = True
                if "direct_state_transition" in dev["EntityInfo"]:
                    dst = dev["EntityInfo"]["direct_state_transition"]
                    del dev["EntityInfo"]["direct_state_transition"]
                if dst:
                    self.logger.info(
                        "Device states will change directly based on payload commands"
                    )
                else:
                    self.logger.info(
                        "Device state changes must be managed via binder actions"
                    )

                if "device" in dev["EntityInfo"]:
                    dev["EntityInfo"]["device"]["via_device"] = (
                        self.dgb_context.device_registry["service"]
                    )
                if dev["EntityInfo"]["component"] == "cover":
                    self.configure_cover(dev, dst)
                elif dev["EntityInfo"]["component"] == "valve":
                    self.configure_valve(dev, dst)
                elif dev["EntityInfo"]["component"] == "sensor":
                    self.configure_sensor(dev, True)
                elif dev["EntityInfo"]["component"] == "switch":
                    self.configure_switch(dev, dst)
                elif dev["EntityInfo"]["component"] == "light":
                    self.configure_light(dev, dst)
                elif dev["EntityInfo"]["component"] == "button":
                    self.configure_button(dev, dst)
                elif dev["EntityInfo"]["component"] == "text":
                    self.configure_text(dev, dst)
                elif dev["EntityInfo"]["component"] == "number":
                    self.configure_number(dev, dst)
                elif dev["EntityInfo"]["component"] == "select":
                    self.configure_select(dev, dst)
                elif dev["EntityInfo"]["component"] == "binary_sensor":
                    self.configure_binary_sensor(dev, True)
                else:
                    self.logger.warning(
                        "Unknown component '{}', skipping this configuration".format(
                            dev["EntityInfo"]["component"]
                        )
                    )
            else:
                self.logger.warning(
                    "No component or unique_id in EntityInfo, skipping this configuration {}".format(
                        dev["EntityInfo"]
                    )
                )
        else:
            self.logger.warning("No EntityInfo in payload, skipping this configuration")

    def _handle_existing_device(
        self,
        unique_id: str,
        policy: DuplicatePolicy,
    ) -> bool:
        """
        Check whether a binding already exists in durable_rules and apply policy.

        Returns:
            True  -> caller may proceed with adding the binding
            False -> caller must skip adding
        """

        if self.dgb_context.get_object(unique_id) is None:
            return True

        if policy == DuplicatePolicy.SKIP:
            self.logger.warning(
                f"Device with unique_id '{unique_id}' already exists -- skipping"
            )
            return False

        # if policy == DuplicatePolicy.REPLACE:
        #     self.logger.warning(
        #         f"Device with unique_id '{unique_id}' already exists -- replacing"
        #     )
        #     self._remove_device(unique_id)
        #     return True

        self.logger.warning(
            f"Device with unique_id '{unique_id}' already exists -- unknown policy '{policy}', skipping"
        )
        return False

    def _record_state_if_required(self, unique_id: str, args: dict[str, list]) -> None:
        if self.dgb_context.is_retain_required(unique_id):
            self.dgb_context.publish_state_to_retain(unique_id, "set_state", args)

    def _set_cover_state(
        self, device: Discoverable, dst: bool, state_name: str, state: str
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported cover state name for %s: %r", unique_id, state_name
            )
            return False
        if state == device._entity.payload_open:
            if dst:
                device.open()
        elif state == device._entity.payload_close:
            if dst:
                device.closed()
        elif state == device._entity.payload_stop:
            if dst:
                device.stopped()
        else:
            self.logger.warning(
                "Unsupported cover payload for %s: %r", unique_id, state
            )
            return False

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_valve_state(
        self, device: Discoverable, dst: bool, state_name: str, state: str | int
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name not in {"state", "position"}:
            self.logger.warning(
                "Unsupported valve state name for %s: %r", unique_id, state_name
            )
            return False

        if state == device._entity.payload_open:
            if dst:
                device.open()
        elif state == device._entity.payload_close:
            if dst:
                device.closed()
        elif state == device._entity.payload_stop:
            if dst:
                device.stopped()
        else:
            state_name = "position"
            try:
                state = int(state)
            except (TypeError, ValueError):
                self.logger.exception(
                    "Wrong payload type for valve %s: %r", unique_id, state
                )
                return False
            if dst:
                device.position(state)

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_switch_state(
        self, device: Discoverable, dst: bool, state_name: str, state: str
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported switch state name for %s: %r", unique_id, state_name
            )
            return False
        if state == device._entity.payload_on:
            if dst:
                device.on()
        elif state == device._entity.payload_off:
            if dst:
                device.off()
        else:
            self.logger.warning(
                "Unsupported switch payload for %s: %r", unique_id, state
            )
            return False

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_text_state(
        self, device: Discoverable, dst: bool, state_name: str, state: str
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported text state name for %s: %r", unique_id, state_name
            )
            return False
        if dst:
            device.set_text(state)

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_number_state(
        self, device: Discoverable, dst: bool, state_name: str, state: float
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported number state name for %s: %r", unique_id, state_name
            )
            return False
        if dst:
            device.set_value(state)

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_select_state(
        self, device: Discoverable, dst: bool, state_name: str, state: str
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported select state name for %s: %r", unique_id, state_name
            )
            return False
        if dst:
            device.select_option(state)

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_sensor_state(
        self,
        device: Discoverable,
        dst: bool,
        state_name: str,
        state: bytes | str | float,
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported sensor state name for %s: %r", unique_id, state_name
            )
            return False
        device.set_state(state)

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def _set_binary_sensor_state(
        self,
        device: Discoverable,
        dst: bool,
        state_name: str,
        state: bool | int | str,
    ) -> bool:
        unique_id = str(device._entity.unique_id)
        if state_name != "state":
            self.logger.warning(
                "Unsupported binary_sensor state name for %s: %r", unique_id, state_name
            )
            return False
        normalized = str(state).lower().strip()
        if normalized in {"on", "1", "true"}:
            device.on()
        elif normalized in {"off", "0", "false"}:
            device.off()
        else:
            self.logger.warning(
                "Unsupported binary_sensor payload for %s: %r", unique_id, state
            )
            return False

        args = {"args": [{"state_name": state_name, "state": state}]}
        self._record_state_if_required(unique_id, args)
        return True

    def configure_cover(self, payload, dst: bool):
        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("cover has time_based_state, adding to settings")
            # time_based_state = True
            # time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        cover_info = sensors.CoverInfo(**payload["EntityInfo"])

        settings = Settings(mqtt=self.mqtt_settings, entity=cover_info)
        callback = build_callback(cover_info, self.dgb_context, dst)
        device = sensors.Cover(settings, callback)
        set_state = partial(self._set_cover_state, device, dst)

        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {
                "open": device.open,
                "closed": device.closed,
                "stopped": device.stopped,
                "opening": device.opening,
                "closing": device.closing,
                "set_state": set_state,
            },
        )
        self.finalize_device(device)

    def configure_valve(self, payload, dst: bool):
        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("valve has time_based_state, adding to settings")
            # time_based_state = True
            # time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        valve_info = sensors.ValveInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=valve_info)
        callback = build_callback(valve_info, self.dgb_context, dst)
        device = sensors.Valve(settings, callback)
        set_state = partial(self._set_valve_state, device, dst)

        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {
                "open": device.open,
                "closed": device.closed,
                "opening": device.opening,
                "closing": device.closing,
                "position": device.position,
                "set_state": set_state,
            },
        )
        self.finalize_device(device)

    def configure_sensor(self, payload, dst: bool):
        self.logger.info("creating sensor")
        sensor_info = sensors.SensorInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=sensor_info)
        device = sensors.Sensor(settings)
        set_state = partial(self._set_sensor_state, device, dst)
        self.dgb_context.add_object(
            str(device._entity.unique_id), device, {"set_state": set_state}
        )
        self.finalize_device(device)

    def configure_switch(self, payload, dst: bool):
        switch_info = sensors.SwitchInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=switch_info)
        callback = build_callback(switch_info, self.dgb_context, dst)
        device = sensors.Switch(settings, callback)
        set_state = partial(self._set_switch_state, device, dst)
        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {"on": device.on, "off": device.off, "set_state": set_state},
        )
        self.finalize_device(device)

    def configure_light(self, payload, dst: bool):
        pass

    def configure_button(self, payload, dst: bool):
        pass

    def configure_text(self, payload, dst: bool):
        text_info = sensors.TextInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=text_info)
        callback = build_callback(text_info, self.dgb_context, dst)
        device = sensors.Text(settings, callback)
        set_state = partial(self._set_text_state, device, dst)

        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {"set_text": device.set_text, "set_state": set_state},
        )
        self.finalize_device(device)

    def configure_number(self, payload, dst: bool):
        number_info = sensors.NumberInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=number_info)
        callback = build_callback(number_info, self.dgb_context, dst)
        device = sensors.Number(settings, callback)
        set_state = partial(self._set_number_state, device, dst)

        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {"set_value": device.set_value, "set_state": set_state},
        )
        self.finalize_device(device)

    def configure_select(self, payload, dst: bool):
        select_info = sensors.SelectInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=select_info)
        callback = build_callback(select_info, self.dgb_context, dst)
        device = sensors.Select(settings, callback)
        set_state = partial(self._set_select_state, device, dst)

        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {"select_option": device.select_option, "set_state": set_state},
        )
        self.finalize_device(device)

    def configure_binary_sensor(self, payload, dst: bool):
        binarysensor_info = sensors.BinarySensorInfo(**payload["EntityInfo"])
        settings = Settings(mqtt=self.mqtt_settings, entity=binarysensor_info)
        callback = build_callback(binarysensor_info, self.dgb_context, dst)
        device = sensors.BinarySensor(settings, callback)
        set_state = partial(self._set_binary_sensor_state, device, dst)
        self.dgb_context.add_object(
            str(device._entity.unique_id),
            device,
            {"on": device.on, "off": device.off, "set_state": set_state},
        )
        self.finalize_device(device)

    def finalize_device(self, device: Discoverable):
        device.availability_topic = self.dgb_context.availability_topic_ns
        device.write_config()
        # device.set_availability(True) # build in function does curently not use retain=True
        # device._update_state(state="online", topic=device.availability_topic, retain=True)

        self.logger.info(
            f"Device of type '{device._entity.component}' with unique_id '{device._entity.unique_id}' created and set discoverable."
        )


def build_callback(
    entity: EntityType,
    dgb_context: DGBContext,
    dst: bool,
):
    logger = logging.getLogger("DeviceKeeper")

    def callback(client: Client, user_data, message: MQTTMessage):
        payload = message.payload.decode()
        logger.info(
            f"Device of type '{entity.component}' with unique_id '{entity.unique_id}' commanded: {payload}"
        )
        dgb_context.put_to_binder_queue(
            "post", {"unique_id": entity.unique_id, "payload": payload}
        )
        state_transition = dgb_context.get_functions(str(entity.unique_id)).get(
            "set_state"
        )
        if callable(state_transition):
            state_transition(
                "state", payload
            )  # works for now, though hacky for valve with positions.

    return callback
