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
from ha_mqtt_discoverable import Settings, sensors, EntityType, Discoverable
from paho.mqtt.client import Client, MQTTMessage
from DGB.DGBContext import DGBContext
from typing import Any, Optional
from collections.abc import Callable
# from DGB.Binder import post_event

logging.basicConfig(level="INFO")


class DeviceKeeper(object):
    def __init__(self, mqtt_settings: Settings.MQTT, dgb_context: DGBContext):
        self.entities = []
        self.mqtt_settings = mqtt_settings
        self.dgb_context = dgb_context
        self.logger = logging.getLogger("DeviceKeeper")
        self.logger.info("starting Entitykeeper")

    def new_device(self, dev):
        if "EntityInfo" in dev:
            if "component" in dev["EntityInfo"]:
                self.logger.info(
                    "Creating {} entity '{}'".format(
                        dev["EntityInfo"]["component"], dev["EntityInfo"]["name"]
                    )
                )
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
                    self.configure_sensor(dev, dst)
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
                    self.configure_binary_sensor(dev, dst)
                else:
                    self.logger.warning(
                        "Unknown component '{}', skipping this configuration".format(
                            dev["EntityInfo"]["component"]
                        )
                    )
            else:
                self.logger.warning(
                    "No component in EntityInfo, skipping this configuration {}".format(
                        dev["EntityInfo"]
                    )
                )
        else:
            self.logger.warning("No EntityInfo in payload, skipping this configuration")

    def configure_cover(self, payload, dst: bool):
        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("cover has time_based_state, adding to settings")
            # time_based_state = True
            # time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        cover_info = sensors.CoverInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                if payload == device._entity.payload_open:
                    device.open()
                elif payload == device._entity.payload_close:
                    device.closed()
                elif payload == device._entity.payload_stop:
                    device.stopped()

        callback = build_callback(
            cover_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=cover_info, manual_availability=True
        )

        device = sensors.Cover(settings, callback)

        self.dgb_context.add_device(
            str(device._entity.unique_id),
            device,
            {
                "open": device.open,
                "closed": device.closed,
                "stopped": device.stopped,
                "opening": device.opening,
                "closing": device.closing,
            },
        )
        finalize_device(device)

    def configure_valve(self, payload, dst: bool):
        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("valve has time_based_state, adding to settings")
            # time_based_state = True
            # time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        valve_info = sensors.ValveInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                if payload == device._entity.payload_open:
                    device.open()
                elif payload == device._entity.payload_close:
                    device.closed()
                elif payload == device._entity.payload_stop:
                    pass
                else:
                    try:
                        payload = int(payload)
                        device.position(payload)
                    except Exception as e:
                        self.logger.error("Wrong payload type: %s", e)

        callback = build_callback(
            valve_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=valve_info, manual_availability=True
        )
        device = sensors.Valve(settings, callback)

        self.dgb_context.add_device(
            str(device._entity.unique_id),
            device,
            {
                "open": device.open,
                "closed": device.closed,
                "opening": device.opening,
                "closing": device.closing,
                "position": device.position,
            },
        )
        finalize_device(device)

    def configure_sensor(self, payload, dst: bool):
        self.logger.info("creating sensor")
        sensor_info = sensors.SensorInfo(**payload["EntityInfo"])
        settings = Settings(
            mqtt=self.mqtt_settings, entity=sensor_info, manual_availability=True
        )
        device = sensors.Sensor(settings)
        self.dgb_context.add_device(
            str(device._entity.unique_id), device, {"set_state": device.set_state}
        )
        finalize_device(device)

    def configure_switch(self, payload, dst: bool):
        switch_info = sensors.SwitchInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                if payload == device._entity.payload_on:
                    device.on()
                elif payload == device._entity.payload_off:
                    device.off()

        callback = build_callback(
            switch_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=switch_info, manual_availability=True
        )
        device = sensors.Switch(settings, callback)
        self.dgb_context.add_device(
            str(device._entity.unique_id), device, {"on": device.on, "off": device.off}
        )
        finalize_device(device)

    def configure_light(self, payload, dst: bool):
        pass

    def configure_button(self, payload, dst: bool):
        pass

    def configure_text(self, payload, dst: bool):
        text_info = sensors.TextInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                device.set_text(payload)

        callback = build_callback(
            text_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=text_info, manual_availability=True
        )
        device = sensors.Text(settings, callback)

        self.dgb_context.add_device(
            str(device._entity.unique_id), device, {"set_text": device.set_text}
        )
        finalize_device(device)

    def configure_number(self, payload, dst: bool):
        number_info = sensors.NumberInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                try:
                    payload = int(payload)
                    device.set_value(payload)
                except Exception as e:
                    self.logger.error("Wrong payload type: %s", e)

        callback = build_callback(
            number_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=number_info, manual_availability=True
        )
        device = sensors.Number(settings, callback)

        self.dgb_context.add_device(
            str(device._entity.unique_id), device, {"set_value": device.set_value}
        )
        finalize_device(device)

    def configure_select(self, payload, dst: bool):
        select_info = sensors.SelectInfo(**payload["EntityInfo"])

        def state_transition_function(payload: Any, dst: bool):
            if dst:
                device.select_option(payload)

        callback = build_callback(
            select_info, self.dgb_context, dst, state_transition_function
        )
        settings = Settings(
            mqtt=self.mqtt_settings, entity=select_info, manual_availability=True
        )
        device = sensors.Select(settings, callback)

        self.dgb_context.add_device(
            str(device._entity.unique_id),
            device,
            {"select_option": device.select_option},
        )
        finalize_device(device)

    def configure_binary_sensor(self, payload, dst: bool):
        binarysensor_info = sensors.BinarySensorInfo(**payload["EntityInfo"])
        settings = Settings(
            mqtt=self.mqtt_settings, entity=binarysensor_info, manual_availability=True
        )
        device = sensors.BinarySensor(settings)
        self.dgb_context.add_device(
            str(device._entity.unique_id), device, {"on": device.on, "off": device.off}
        )
        finalize_device(device)


def build_callback(
    entity: EntityType,
    dgb_context: DGBContext,
    dst: bool,
    state_transition_function: Optional[Callable[[Any, bool], None]],
):
    logger = logging.getLogger("DeviceKeeper")

    def callback(client: Client, user_data, message: MQTTMessage):
        payload = message.payload.decode()
        logger.info(
            "Device of type '{}' with unique_id '{}' commanded: {}".format(
                entity.component, entity.unique_id, payload
            )
        )
        dgb_context.put_to_binder_queue(
            "post", {"unique_id": entity.unique_id, "payload": payload}
        )
        if state_transition_function:
            state_transition_function(payload, dst)

    return callback


def finalize_device(device: Discoverable):
    logger = logging.getLogger("DeviceKeeper")
    device.write_config()
    device.set_availability(True)
    logger.info(
        "Device of type '{}' with unique_id '{}' created and set discoverable.".format(
            device._entity.component, device._entity.unique_id
        )
    )
