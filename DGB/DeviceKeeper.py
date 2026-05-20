#!/usr/bin/env python
# encoding: utf-8
"""
Device keeper to manage home assistant device and entity configurations.

Jeroen van Oosterhout, 24-12-2025
"""

import logging
from ha_mqtt_discoverable import Settings, sensors
from paho.mqtt.client import Client, MQTTMessage
from DGB.DGBContext import DGBContext
# from DGB.Binder import post_event

logging.basicConfig(level="INFO")


class DeviceKeeper(object):
    def __init__(self, mqtt_settings: Settings, dgb_context: DGBContext):
        self.entities = []
        self.mqtt_settings = mqtt_settings
        self.dgb_context = dgb_context
        self.logger = logging.getLogger("DeviceKeeper")
        self.logger.info("starting Entitykeeper")

    def new_device(self, dev):
        if "EntityInfo" in dev:
            if "component" in dev["EntityInfo"]:
                if "device" in dev["EntityInfo"]:
                    dev["EntityInfo"]["device"]["via_device"] = "dgb-app"
                if dev["EntityInfo"]["component"] == "cover":
                    self.configure_cover(dev)
                elif dev["EntityInfo"]["component"] == "sensor":
                    self.configure_sensor(dev)
                elif dev["EntityInfo"]["component"] == "switch":
                    self.configure_switch(dev)
                elif dev["EntityInfo"]["component"] == "light":
                    self.configure_light(dev)
                elif dev["EntityInfo"]["component"] == "button":
                    self.configure_button(dev)
                elif dev["EntityInfo"]["component"] == "text":
                    self.configure_text(dev)
                elif dev["EntityInfo"]["component"] == "number":
                    self.configure_number(dev)
                elif dev["EntityInfo"]["component"] == "select":
                    self.configure_select(dev)
                elif dev["EntityInfo"]["component"] == "binary_sensor":
                    self.configure_binary_sensor(dev)
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

    def configure_cover(self, payload):
        self.logger.info("creating cover")
        # time_based_state = False
        direct_state_transition = True
        state_transition_after_action_succes = False

        if "time_based_state" in payload["EntityInfo"]:
            self.logger.info("cover has time_based_state, adding to settings")
            # time_based_state = True
            # time_based_duration = payload["EntityInfo"]["time_based_state"]
            del payload["EntityInfo"]["time_based_state"]

        if "direct_state_transition" in payload["EntityInfo"]:
            direct_state_transition = payload["EntityInfo"]["direct_state_transition"]
            del payload["EntityInfo"]["direct_state_transition"]

        # if "state_transition_after_action_succes" in payload["EntityInfo"]:
        #     state_transition_after_action_succes = payload["EntityInfo"]["state_transition_after_action_succes"]
        #     del payload["EntityInfo"]["state_transition_after_action_succes"]

        if direct_state_transition:
            self.logger.info(
                "cover states will change directly based on paload commands"
            )
        else:
            if state_transition_after_action_succes:
                self.logger.info(
                    "cover state changes occure after succesfull binder action"
                )
            else:
                self.logger.info(
                    "cover state changes must be managed via binder actions"
                )

        cover_info = sensors.CoverInfo(**payload["EntityInfo"])

        def my_callback(client: Client, user_data, message: MQTTMessage):
            payload = message.payload.decode()
            self.logger.info(
                "Cover {} commanded: {}".format(device._entity.unique_id, payload)
            )

            self.dgb_context.put_to_binder_queue(
                "post", {"unique_id": device._entity.unique_id, "payload": payload}
            )

            if direct_state_transition:
                if payload == device._entity.payload_open:
                    device.opening()
                    device.open()
                elif payload == device._entity.payload_close:
                    device.closing()
                    device.closed()
                elif payload == device._entity.payload_stop:
                    device.stopped()

        device = sensors.Cover(
            Settings(
                mqtt=self.mqtt_settings, entity=cover_info, manual_availability=True
            ),
            my_callback,
        )

        self.dgb_context.add_device(
            device._entity.unique_id,
            device,
            {
                "open": device.open,
                "closed": device.closed,
                "stopped": device.stopped,
                "opening": device.opening,
                "closing": device.closing,
            },
        )
        device.closed()
        device.set_availability(True)
        self.logger.info(
            "Cover '{}' with unique_id '{}' made and closed.".format(
                device._entity.name, device._entity.unique_id
            )
        )

    def configure_sensor(self, payload):
        self.logger.info("creating sensor")
        sensor_info = sensors.SensorInfo(**payload["EntityInfo"])
        device = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings, entity=sensor_info, manual_availability=True
            ),
        )
        self.dgb_context.add_device(
            device._entity.unique_id, device, {"set_state": device.set_state}
        )
        self.logger.info(
            "Sensor '{}' with unique_id '{}' made and set to ''.".format(
                device._entity.name, device._entity.unique_id
            )
        )
        device.set_state("")
        device.set_availability(True)

    def configure_switch(self, payload):
        self.logger.info("creating switch")
        direct_state_transition = True

        if "direct_state_transition" in payload["EntityInfo"]:
            direct_state_transition = payload["EntityInfo"]["direct_state_transition"]
            del payload["EntityInfo"]["direct_state_transition"]

        switch_info = sensors.SwitchInfo(**payload["EntityInfo"])

        def my_callback(client: Client, user_data, message: MQTTMessage):
            payload = message.payload.decode()
            self.logger.info(
                "turn switch {}: {}".format(device._entity.unique_id, payload)
            )
            self.dgb_context.put_to_binder_queue(
                "post", {"unique_id": device._entity.unique_id, "payload": payload}
            )
            if direct_state_transition:
                if payload == device._entity.payload_on:
                    device.on()
                elif payload == device._entity.payload_off:
                    device.off()

        device = sensors.Switch(
            Settings(
                mqtt=self.mqtt_settings,
                entity=switch_info,
                manual_availability=True,
            ),
            my_callback,
        )
        self.dgb_context.add_device(
            device._entity.unique_id, device, {"on": device.on, "off": device.off}
        )
        device.off()
        device.set_availability(True)
        self.logger.info(
            "Switch '{}' with unique_id '{}' made and turned off.".format(
                device._entity.name, device._entity.unique_id
            )
        )

    def configure_light(self, payload):
        pass

    def configure_button(self, payload):
        pass

    def configure_text(self, payload):
        pass

    def configure_number(self, payload):
        pass

    def configure_select(self, payload):
        pass

    def configure_binary_sensor(self, payload):
        self.logger.info("creating binary sensor")
        binarysensor_info = sensors.BinarySensorInfo(**payload["EntityInfo"])
        device = sensors.BinarySensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=binarysensor_info,
                manual_availability=True,
            ),
        )
        self.dgb_context.add_device(
            device._entity.unique_id, device, {"on": device.on, "off": device.off}
        )
        self.logger.info(
            "Binary sensor '{}' with unique_id '{}' made and deactivated.".format(
                device._entity.name, device._entity.unique_id
            )
        )
        device.off()
        device.set_availability(True)
