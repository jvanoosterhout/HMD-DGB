#!/usr/bin/env python
# encoding: utf-8
"""
System devices template for HMD-DGB node and service and application monitoring.

Defines two static devices with entities:
1. node device: representing the SBC with hardware metrics (CPU, RAM, uptime, temperature) and controls (reboot)
2. DGB service device: representing the application with metrics (version) and controls (update, restart service)

These devices are on the top of the hierarchical device model and separately from user-defined devices to  provide a standard interface for system monitoring and control.

Basic model
Node (root device)
  ├─ Node entities (SBC info and control)
  └─> Service (Runtime service)
        ├─ Service entities (SBC info and control)
        └─> User defined device
             Entities

Jeroen van Oosterhout, 2026
"""

from __future__ import annotations

import logging
import platform
import socket
from typing import Optional

import pkg_resources
import psutil
from gpiozero import CPUTemperature
from ha_mqtt_discoverable import Settings, DeviceInfo, sensors

from DGB.DGBContext import DGBContext


# Fixed device identifiers - these never change
NODE_ID = "dgb-node"
SERVICE_ID = "dgb-service"


class SystemDevices:
    """
    Manages creation and lifecycle of system devices (platform + service).

    Responsibilities:
    - Create/recreate node device with hardware sensors
    - Create/recreate DGB service device with version/update controls
    - Maintain device ID registry in DGBContext
    - Expose parent device IDs for user-defined devices
    """

    def __init__(
        self,
        mqtt_settings: Settings,
        dgb_context: DGBContext,
        device_name: str,
        location: Optional[str] = None,
        dgb_mqtt_instance: Optional[object] = None,
    ) -> None:
        """
        Initialize system devices manager.

        Args:
            mqtt_settings: MQTT configuration from ha_mqtt_discoverable
            dgb_context: Shared DGB runtime context
            device_name: Base name for the DGB instance (e.g., 'rpi-garage')
            location: Optional Home Assistant location (room/area)
            dgb_mqtt_instance: Reference to DGBMQTT instance for restart callbacks
        """
        self.mqtt_settings = mqtt_settings
        self.dgb_context = dgb_context
        self.device_name = device_name
        self.location = location
        self.dgb_mqtt = dgb_mqtt_instance

        self.logger = logging.getLogger(f"SystemDevices[{device_name}]")
        self.logger.info("SystemDevices initialized")

        # Sensor objects (held for state updates)
        self.cpu_temp: Optional[sensors.Sensor] = None
        self.cpu_usage: Optional[sensors.Sensor] = None
        self.mem_usage: Optional[sensors.Sensor] = None
        self.uptime: Optional[sensors.Sensor] = None

        # Button objects (for state management if needed)
        self.restart_button: Optional[sensors.Button] = None

    def create_devices(self) -> None:
        """
        Create or recreate node and DGB service devices.

        Called once on startup and again if system config changes.
        Clears old device references and rebuilds from scratch.
        """
        self.logger.info("Creating system devices (node + service)")

        # Create node device with hardware sensors
        self._create_node_device()

        # Create service device with version/update controls
        self._create_service_device()

        # Register device IDs in context so user devices can reference them
        self.dgb_context.device_registry = {
            "node": NODE_ID,
            "service": SERVICE_ID,
        }
        self.logger.info(
            "Device registry updated: node=%s, service=%s",
            NODE_ID,
            SERVICE_ID,
        )

    def _create_node_device(self) -> None:
        """Create the node device with hardware monitoring sensors."""
        self.logger.info("Creating node device")

        ip = self._get_ip()
        system = platform.uname()

        device_info = DeviceInfo(
            name=f"{self.device_name} node",
            identifiers=NODE_ID,
            model=system[1],
            manufacturer=system[1],
            sw_version=system[3],
            hw_version=system[4],
            configuration_url=ip,
            suggested_area=self.location,
        )

        # CPU Temperature Sensor
        self.cpu_temp = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="CPU temperature",
                    unit_of_measurement="°C",
                    device_class="temperature",
                    unique_id=f"{self.device_name}_cpu_temp",
                    device=device_info,
                ),
                manual_availability=True,
            )
        )
        self.dgb_context.add_device(self.cpu_temp._entity.unique_id, self.cpu_temp)
        self.cpu_temp.set_availability(True)

        # CPU Usage Sensor
        self.cpu_usage = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="CPU usage",
                    unit_of_measurement="%",
                    unique_id=f"{self.device_name}_cpu_usage",
                    device=device_info,
                ),
                manual_availability=True,
            )
        )
        self.dgb_context.add_device(self.cpu_usage._entity.unique_id, self.cpu_usage)
        self.cpu_usage.set_availability(True)

        # Memory Usage Sensor
        self.mem_usage = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="Memory usage",
                    unit_of_measurement="%",
                    unique_id=f"{self.device_name}_mem_usage",
                    device=device_info,
                ),
                manual_availability=True,
            )
        )
        self.dgb_context.add_device(self.mem_usage._entity.unique_id, self.mem_usage)
        self.mem_usage.set_availability(True)

        # Uptime Sensor
        self.uptime = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="Uptime",
                    unit_of_measurement="h",
                    device_class="duration",
                    unique_id=f"{self.device_name}_uptime",
                    device=device_info,
                ),
                manual_availability=True,
            )
        )
        self.uptime.set_availability(True)
        self.dgb_context.add_device(self.uptime._entity.unique_id, self.uptime)

        self.logger.info("Node device created with 4 sensors")

    def _create_service_device(self) -> None:
        """Create the DGB service device with version and restart button."""
        self.logger.info("Creating DGB service device")

        # Get installed version
        try:
            service_version = pkg_resources.get_distribution("HMD-DGB").version
        except Exception as e:
            self.logger.warning("Could not get service version: %s", e)
            service_version = "unknown"

        device_info = DeviceInfo(
            name=f"DGB {self.device_name} service",
            identifiers=SERVICE_ID,
            model="HMD-DGB",
            manufacturer="J van Oosterhout",
            sw_version=service_version,
            configuration_url="https://github.com/jvanoosterhout/HMD-DGB",
            suggested_area=self.location,
            # Parent device: node must be created first
            via_device=NODE_ID,
        )

        # Version sensor (read-only)
        self.version_sensor = sensors.Sensor(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.SensorInfo(
                    name="Current version",
                    unique_id=f"{self.device_name}_service_version",
                    device=device_info,
                ),
                manual_availability=True,
            )
        )
        self.version_sensor.set_state(service_version)
        self.version_sensor.set_availability(True)
        self.dgb_context.add_device(
            self.version_sensor._entity.unique_id, self.version_sensor
        )

        # Restart button - triggers full service reinitialization
        def restart_callback(client, userdata, message):
            """Callback for restart button press: full service reinit."""
            self.logger.info("Restart button pressed via MQTT")
            if self.dgb_mqtt:
                self._restart_service()
            else:
                self.logger.warning("DGBMQTT instance not available for restart")

        self.restart_button = sensors.Button(
            Settings(
                mqtt=self.mqtt_settings,
                entity=sensors.ButtonInfo(
                    name="Restart service",
                    unique_id=f"{self.device_name}_restart",
                    device=device_info,
                    icon="mdi:restart",
                ),
                manual_availability=True,
            ),
            restart_callback,
        )
        self.restart_button.write_config()
        self.restart_button.set_availability(True)
        self.dgb_context.add_device(
            self.restart_button._entity.unique_id, self.restart_button
        )

        self.logger.info(
            "DGB service device created with version sensor and restart button"
        )

    def update_sensor_values(self) -> None:
        """Update hardware sensor values (called periodically by sensor loop)."""
        if (
            not self.cpu_temp
            or not self.cpu_usage
            or not self.mem_usage
            or not self.uptime
        ):
            self.logger.warning("Sensor objects not initialized")
            return

        try:
            self.cpu_temp.set_state(round(CPUTemperature().temperature, 1))
        except Exception as e:
            self.logger.warning("Could not read CPU temperature: %s", e)

        try:
            self.cpu_usage.set_state(psutil.cpu_percent(interval=1))
        except Exception as e:
            self.logger.warning("Could not read CPU usage: %s", e)

        try:
            self.mem_usage.set_state(psutil.virtual_memory().percent)
        except Exception as e:
            self.logger.warning("Could not read memory usage: %s", e)

        try:
            import time

            self.uptime.set_state(round(time.monotonic() / 3600, 1))
        except Exception as e:
            self.logger.warning("Could not read uptime: %s", e)

    def _restart_service(self) -> None:
        """Trigger service restart: stop, clear devices, and reconnect to MQTT."""
        if not self.dgb_mqtt:
            self.logger.error("Cannot restart: DGBMQTT instance not available")
            return

        self.logger.info("Starting service restart sequence")
        try:
            self.dgb_mqtt.restart()
        except Exception as e:
            self.logger.error("Error during restart: %s", e)

    def get_parent_device_id(self, device_type: str = "service") -> str:
        """
        Get parent device ID for user-defined child devices.

        Args:
            device_type: Type of parent ('service' or 'node')

        Returns:
            Device ID string suitable for via_device in DeviceInfo

        Raises:
            ValueError: If device type unknown or not created
        """
        if device_type == "service":
            return SERVICE_ID
        elif device_type == "node":
            return NODE_ID
        else:
            raise ValueError(f"Unknown device type: {device_type}")

    def name_with_location(self) -> str:
        """Format device name with location suffix if provided."""
        if self.location:
            return f"{self.device_name} ({self.location})"
        return self.device_name

    @staticmethod
    def _get_ip() -> str:
        """Get local IP address for configuration URL."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return f"http://{ip}"
        except Exception as e:
            logging.getLogger("SystemDevices").warning(
                "Could not determine IP address: %s", e
            )
            return "localhost"
