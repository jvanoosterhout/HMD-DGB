# HMD-DGB: Home Assistant MQTT-Discoverable Device GPIO Binder

Control Raspberry Pi GPIO pins via MQTT with automatic Home Assistant discoverable devices. Bridge your hardware to smart home automation through declarative device bindings via durable rules.

The power and uniquesnes of HMD-DGB is twofold:
- it allows to configure complex entities that can rely on multiple sensors and actors like a cover (control open/close/stop, sens is_open/is_closed) or a light (RGBW).
- it allows to manage the node (the RPI/SBC), service and configurations from Home Assistant or an other central location. In that Home Assistant only stores the configurations, no flooding of Home Assistant with helpers or intermediate entities.

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
  - [Hardware & OS](#hardware--os)
  - [Software](#software)
  - [Tested Platforms](#tested-platforms)
- [Installation](#installation)
  - [Option 1: venv](#option-1-venv)
  - [Option 2: Docker](#option-2-docker)
- [Reference documentation](#reference-documentation)
  - [Node & system health & contol](#node--system-health--contol)
  - [Basic configuration](#basic-configuration)
  - [Devices with EntityInfo](#devices-with-entityinfo)
    - [Device](#device)
    - [Basic parameters (for alle entities)](#basic-parameters-for-alle-entities)
    - [Binary sensor](#binary-sensor)
    - [Button](#button)
    - [Camera (not implemented yet)](#camera-not-implemented-yet)
    - [Cover](#cover)
    - [Device trigger (not implemented yet)](#device-trigger-not-implemented-yet)
    - [Image (not implemented yet)](#image-not-implemented-yet)
    - [Light (not implemented yet)](#light-not-implemented-yet)
    - [Lock (not implemented yet)](#lock-not-implemented-yet)
    - [Number](#number)
    - [Select](#select)
    - [Sensor](#sensor)
    - [Switch](#switch)
    - [Text](#text)
    - [Valve](#valve)
  - [Pins with PinInfo](#pins-with-pininfo)
    - [PinIn](#pinin)
    - [PinOut](#pinout)
    - [PinCount](#pincount)
    - [PinNWayOut](#pinnwayout)
  - [Bindings with BindInfo](#bindings-with-bindinfo)
    - [Ruleset](#ruleset)
    - [Rule conditions](#rule-conditions)
    - [Rule run actions](#rule-run-actions)
      - [Log](#log)
      - [timer](#timer)
      - [action](#action)
- [Architecture](#architecture)
- [Ideas for improvement (unsorted in priority)](#ideas-for-improvement-unsorted-in-priority)
- [Known Issues & Limitations](#known-issues--limitations)
  - [First load issue](#first-load-issue)
  - [Loading configurations & runtime](#loading-configurations--runtime)
  - [restart of the system](#restart-of-the-system)
  - [Loading configurations & runtime](#loading-configurations--runtime-1)
  - [Count-Type Pin Device](#count-type-pin-device)
  - [Maintenance/updates of Durable Rules](#maintenanceupdates-of-durable-rules)
- [Contributing](#contributing)
- [Project Status](#project-status)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## Overview

**HMD-DGB** (Home Assistant MQTT-Discoverable Device GPIO Binder) provides a Python-based solution for managing GPIO pins on Raspberry Pi with Home Assistant integration via MQTT discoverable devices. Unique to this package is that it is an end-to-end solution reling on the [ha-mqtt-discoverable](https://github.com/unixorn/ha-mqtt-discoverable) package for MQTT Discovery and [Durable Rules](https://github.com/jruizgit/rules) to bind these devices to [GPIOzero](https://github.com/gpiozero/gpiozero) pins. This eliminats manual programing via easy json configuration. While developping this package over the years, I learned that this resembles several aspects of ESP Home.

Future vision is to make a flexable solution to configure and manage edge devices/nodes like Raspberry PI while haveing near-zero need to touch the code on the node. Think of installing the OS including the initial package setup, and then only work from Home Assistant to e.g. update the package or configureing GPIO, devices and bindings.

The system consists of four core concepts:

- **MQTT Discoverable Devices**: Devices that automatically appear in Home Assistant via MQTT discovery protocol
- **Durable Binding Rules**: Define relationships and actions between physical GPIO pins and Home Assistant devices
- **GPIOzero Devices**: configuration of GPIO pins to proform meaningfull action in the real world
- **on the fly configuration**: send device, binding and GPIO configurations over MQTT to your Raspberry Pi (you still need to install this package, configure HA, and setup the MQTT service)

[top](#table-of-contents)

## Requirements

### Hardware & OS

- **Raspberry Pi**: Pi 4 or Pi Zero 2 W (or compatible board)
  - Pi Zero may require to buil some packages like psutil
  ```bash
  sudo apt install -y gcc python3-dev build-essential
  ```
- **Operating System**: Bookworm or newer recommended
  - Bullseye may work with GPIOZERO fallback to RPI.GPIO
  - Not tested on older versions

### Software

- **Python**: 3.10-3.12
- **MQTT Broker**: Mosquitto or compatible
- **Home Assistant**: 2023.1 or later

### Tested Platforms

- Raspberry Pi 4 with Bookworm (64-bit, desktop) and Python 3.11.2
- Raspberry Pi Zero 2 W with Bookworm (32-bit, lite) and Python 3.10.0

[top](#table-of-contents)

## Installation

### Option 1: venv

```bash
# Create project directory and virtual environment
mkdir hmd-dgb-project && cd hmd-dgb-project
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
# Install from repository
pip install git+https://github.com/jvanoosterhout/HMD-DGB.git
python -m DGB.DGBservice --name "my-service-name" --broker "my-broker" [--port "my-port"] [--topic "my-topic] [--username "my-username"] [--password "my-password"] [--location "my-location"]
```

[top](#table-of-contents)

### Option 2: Docker

Docker support is on the roadmap simplified deployment and consistency across systems.

[top](#table-of-contents)

## Reference documentation

### Node & system health & contol

As the HMD-DGB service is started, it creates a descoverable DGB node and DGB service for the given service-name. Both devices have sensors,  controls and some basic information.

DGB node for service-name:
- CPU usage
- RAM usage
- CPU temperature
- Uptime

DGB service for service-name:
- Current software version installed
- Latest software version available
- Soft restart (set all entities to unavailable, restart service, leave other MQTT messages untoughed)
- Hard restart (clear all MQTT messages related to this service including its config topic and restart service)

In DGB, your own devices can only be configured inside an entity json with the "device" key. DGB alters this device json slichtly: it overrides/creates the "via_device" key to the uniqued id of the DGB service device.

[top](#table-of-contents)

### Basic configuration

Once the HMD-DGB service runs on a pi/SBC, and it is connected to a MQTT broker (with Home Assistant as subscriber), the next step is as simple as publishing a configuration MQTT message to the config topic "config/{name}/devices/". Such a massage can configure devices (i.e Home Assistant entities that are optionally grouped in devices), GPIO pins and bindings between the first two. The message should be a json payload structured like this:

```json
{
  "Devices": [
    {"EntityInfo": EntityInfo},
  ],
  "Pins": [
    {"PinInfo": pinoutinfo},
    ],
  "Bindings": [
    {"BindInfo": binding_info},
  ],
}
```
How to fill this message is explained in the next sections.

[top](#table-of-contents)

### Devices with EntityInfo

In this section you can find the configuration parameters and defaults for Home Assisntant discoverable devices. In the background the HA devices are configured and managed by the [ha-mqtt-discoverable](https://github.com/unixorn/ha-mqtt-discoverable) package. HMD-DGB provides an implementation of this package with some aditional parameters. These extra parameters will be indicated behind the ha-mqtt-discoverable parameters. Aditionally you find the run.action.call ids and run.action.args that can be used in binding via [Durable Rules](https://github.com/jruizgit/rules).

[top](#table-of-contents)

#### Device

A device is a special entity in Home Assistant and thus displayed separately form other discoverable devices. In fact, this is the only device, other sections describe Home Assistant entities, and entities can belong to a device. Home Assistant's own definition:
From the [Home Assistant documentation](https://www.home-assistant.io/getting-started/concepts-terminology/):
> Devices are a logical grouping for one or more entities. A device may represent a physical device, which can have one or more sensors. The sensors appear as entities associated with the device. For example, a motion sensor is represented as a device. It may provide motion detection, temperature, and light levels as entities. Entities have states such as detected when motion is detected and clear when there is no motion.

HMD parameters:

| Parameter          | Description                                                                 | Type               | Default  |
|-------------------|-----------------------------------------------------------------------------|--------------------|----------|
| name              | Name of the device.                                                         | str                | required |
| model             | Model of the device.                                                        | str                | optional |
| manufacturer      | Manufacturer of the device.                                                 | str                | optional |
| sw_version        | Firmware version of the device.                                             | str                | optional |
| hw_version        | Hardware version of the device.                                             | str                | optional |
| identifiers       | A list of IDs that uniquely identify the device (e.g. a serial number).     | list[str] \| str   | optional |
| connections       | A list of connections to the outside world as tuples `[type, identifier]`.  | list[tuple]        | optional |
| configuration_url | Link to a webpage to manage device configuration (HTTP or HTTPS).           | str                | optional |
| suggested_area    | Suggested name for the area where the device is located.                    | str                | optional |
| via_device        | Identifier of a device that routes messages between this device and Home Assistant (e.g. hub or parent device). | str                | optional |

```json
{
  "name": "Example Device",
  "model": "Model X",
  "manufacturer": "Example Corp",
  "sw_version": "1.0.0",
  "hw_version": "revA",
  "identifiers": ["SN-123456"],
  "connections": [["mac", "00:11:22:33:44:55"]],
  "configuration_url": "http://192.168.1.10",
  "suggested_area": "Living Room",
  "via_device": "example_hub"
}
```

In DGB, devices can only be configured inside an entity with the "device" key. The value of this key is the above json. DGB alters this json slichtly: it overrides/creates the "via_device" key to the uniqued id of the DGB service device.

[top](#table-of-contents)

#### Basic parameters (for alle entities)

Parameters that all devices (i.e. entities) have, and can thuse be appended to the EntityInfo configuration of each device (i.e. entities) in the following subsections.

| Parameter           | Description                                                                 | Type       | Default  |
|--------------------|-----------------------------------------------------------------------------|------------|----------|
| component          | One of the supported MQTT components, for instance `binary_sensor`.         | str        | required |
| name               | Name of the sensor inside Home Assistant.                                   | str        | required |
| device             | Information about the device this sensor belongs to.                        | DeviceInfo | optional |
| device_class       | Sets the class of the device, changing the device state and icon displayed on the frontend. | str        | optional |
| enabled_by_default | Flag which defines if the entity should be enabled when first added.        | bool       | optional |
| entity_category    | Classification of a non-primary entity.                                     | str        | optional |
| expire_after       | Number of seconds after which the sensor’s state expires if it is not updated. After expiry, the sensor’s state becomes unavailable. By default, the sensor state never expires. | int        | optional |
| force_update       | Sends update events even if the value has not changed. Useful for meaningful value graphs in history. | bool       | optional |
| icon               | Icon for the sensor.                                                        | str        | optional |
| object_id          | Set this to generate the `entity_id` in Home Assistant instead of using `name`. | str        | optional |
| qos                | The maximum QoS level to be used when receiving messages.                   | int        | optional |
| unique_id          | Set this to enable editing the sensor from the Home Assistant UI and to integrate with a device. | str        | optional |
| display_name       | Display name for the Home Assistant UI. If not set, `name` is used.         | str        | optional |


```json
{
  "component": "sensor",
  "name": "Example Sensor",
  "device_class": "temperature",
  "enabled_by_default": true,
  "entity_category": "diagnostic",
  "expire_after": 60,
  "force_update": false,
  "icon": "mdi:thermometer",
  "object_id": "example_sensor",
  "qos": 0,
  "unique_id": "example_sensor_001",
  "display_name": "Example Sensor"
}
```

[top](#table-of-contents)

#### Binary sensor

HMD parameters:

| Parameter    | Description                                                                 | Type | Default |
|-------------|-----------------------------------------------------------------------------|------|---------|
| component   | One of the supported MQTT components. For this sensor, defaults to `binary_sensor`. | str  | `binary_sensor` |
| off_delay   | For sensors that only send state updates (e.g. PIR sensors), sets a delay in seconds after which the sensor state is automatically updated back to `off`. | int  | optional |
| payload_off | Payload to send for the OFF state.                                          | str  | `off` |
| payload_on  | Payload to send for the ON state.                                           | str  | `on` |

```json
{
  "component": "binary_sensor",
  "payload_on": "on",
  "payload_off": "off",
  "off_delay": 30
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| off   | Set binary sensor to off.                                                      |   |  |   |
| on   | Set binary sensor to off.                                                     |   |  |   |

[top](#table-of-contents)

#### Button

HMD parameters:

| Parameter      | Description                                                                 | Type | Default |
|---------------|-----------------------------------------------------------------------------|------|---------|
| component     | One of the supported MQTT components. For this entity, defaults to `button`. | str  | `button` |
| payload_press | Payload sent to trigger the button press.                                   | str  | `PRESS` |
| retain        | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |

```json
{
  "component": "button",
  "payload_press": "PRESS",
  "retain": false
}
```

[top](#table-of-contents)

#### Camera (not implemented yet)

HMD parameters:

| Parameter        | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| component        | The MQTT component type for this entity.                                    | str  | `camera` |
| topic            | MQTT topic subscribed to receive image payloads.                            | str  | required |
| retain           | Defines whether the published MQTT message should have the retain flag set. | bool | optional |
| image_encoding   | Encoding of received image payloads. Set to `b64` to enable base64 decoding. If not set, the payload must be raw binary image data. | str | optional |

```json
{
  "component": "camera",
  "topic": "example/camera/image",
  "retain": false,
  "image_encoding": "b64"
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| set_payload   | Update the image payload of the camera.                                  | image_payload  | bytes or str |  image payload to be published to topic |

[top](#table-of-contents)

#### Cover

HMD parameters:

| Parameter         | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| component        | One of the supported MQTT components. For this entity, defaults to `cover`. | str  | `cover` |
| optimistic       | Flag that defines whether the cover works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool | optional |
| payload_close    | Command payload used to close the cover.                                    | str  | `CLOSE` |
| payload_open     | Command payload used to open the cover.                                     | str  | `OPEN` |
| payload_stop     | Command payload used to stop the cover.                                     | str  | `STOP` |
| position_closed  | Numeric value that represents the fully closed position.                   | int  | `0` |
| position_open    | Numeric value that represents the fully open position.                     | int  | `100` |
| state_open       | Payload that represents the open state.                                    | str  | `open` |
| state_opening    | Payload that represents the opening state.                                 | str  | `opening` |
| state_closed     | Payload that represents the closed state.                                  | str  | `closed` |
| state_closing    | Payload that represents the closing state.                                 | str  | `closing` |
| state_stopped    | Payload that represents the stopped state.                                 | str  | `stopped` |
| retain           | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |

```json
{
  "component": "cover",
  "optimistic": false
  "payload_open": "OPEN",
  "payload_close": "CLOSE",
  "payload_stop": "STOP",
  "position_open": 100,
  "position_closed": 0,
  "state_open": "open",
  "state_opening": "opening",
  "state_closed": "closed",
  "state_closing": "closing",
  "state_stopped": "stopped",
  "retain": false
}
```

DGB parameters:

| Parameter         | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| time_based_state        | Cover position is calculated based on the active time | bool  | `False` |
| direct_state_transition  | If True, cover states will change directly based on paload commands, otherwise states must be managed via the binder with run.action.call | bool | `True` |

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| open        | Set cover state to open                                                      |          |      |             |
| closed      | Set cover state to closed                                                      |          |      |             |
| closing     | Set cover state to closing                                                      |          |      |             |
| opening     | Set cover state to opening                                                      |          |      |             |
| stopped     | Set cover state to stopped                                                      |          |      |             |

[top](#table-of-contents)

#### Device trigger (not implemented yet)

HMD parameters:

| Parameter        | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| component        | The MQTT component type for this entity.                                    | str  | `device_automation` |
| automation_type  | Type of automation. Must be `trigger`.                                      | str  | `trigger` |
| payload          | Optional payload to match against the payload received on the topic.       | str  | optional |
| type             | The type of the trigger.                                                    | str  | required |
| subtype          | The subtype of the trigger.                                                 | str  | required |

```json
{
  "component": "device_automation",
  "automation_type": "trigger",
  "type": "button_short_press",
  "subtype": "button_1",
  "payload": "PRESS"
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| trigger   | Generate a device trigger event                                  | payload  | str |  Custom payload to send in the trigger topic |

[top](#table-of-contents)

#### Image (not implemented yet)

HMD parameters:

| Parameter        | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| component        | The MQTT component type for this entity.                                    | str  | `image` |
| url_topic        | MQTT topic used to receive an image URL. Cannot be used together with `image_topic`. | str  | optional |
| image_topic      | MQTT topic used to receive raw image payloads. Cannot be used together with `url_topic`. | str  | optional |
| image_encoding   | Encoding of image payloads. Set to `b64` to enable base64 decoding. If not set, payloads must be raw binary data. | str | optional |
| content_type     | Content type to use when sending image payloads. Cannot be used together with `url_topic`. | str | optional |

Example using image_topic (binary or base64 payload)

```json
{
  "component": "image",
  "image_topic": "example/image/raw",
  "image_encoding": "b64",
  "content_type": "image/jpeg"
}
```

Alternative example using url_topic

```json
{
  "component": "image",
  "url_topic": "example/image/url"
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| set_url   |  Update the image URL.                              | image_url  | str |  image URL to be published to url_topic |
| set_payload   |   Update the image payload.                      | image_payload  | bytes or str |  image payload to be published to image_topic |

[top](#table-of-contents)

#### Light (not implemented yet)

HMD parameters:

| Parameter                | Description                                                                 | Type        | Default |
|-------------------------|-----------------------------------------------------------------------------|-------------|---------|
| component               | One of the supported MQTT components. For this entity, defaults to `light`. | str         | `light` |
| state_schema            | Sets the schema of the state topic (the `schema` field in the configuration). | str         | `json` |
| optimistic              | Flag that defines whether the light works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool        | optional |
| payload_off             | Payload that represents the OFF state. Used both for comparing against values received on `state_topic` and for sending the OFF command to the `command_topic`. | str         | `OFF` |
| payload_on              | Payload that represents the ON state. Used both for comparing against values received on `state_topic` and for sending the ON command to the `command_topic`. | str         | `ON` |
| brightness              | Flag that defines whether the light supports brightness control.             | bool        | `False` |
| color_mode              | Flag that defines whether the light supports color mode.                     | bool        | optional |
| supported_color_modes   | List of supported color modes. Required if `color_mode` is set. See Home Assistant documentation for valid values. | list[str]   | optional |
| effect                  | Flag that defines whether the light supports effects.                        | bool        | `False` |
| effect_list             | List of supported effects. Required if `effect` is set.                     | str \| list | optional |
| retain           | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |

```json
{
  "component": "light",
  "state_schema": "json",
  "optimistic": false,
  "payload_on": "ON",
  "payload_off": "OFF",
  "brightness": true,
  "color_mode": true,
  "supported_color_modes": ["rgb", "color_temp"],
  "effect": true,
  "effect_list": ["rainbow", "pulse", "flash"],
  "retain": false
}
```

DGB binder run.action.call and (optional) run.action.args:

TODO: make table

[top](#table-of-contents)

#### Lock (not implemented yet)

HMD parameters:

| Parameter        | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| component        | One of the supported MQTT components. For this entity, defaults to `lock`.  | str  | `lock` |
| optimistic       | Flag that defines whether the lock works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool | optional |
| retain           | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |
| payload_lock     | Command payload used to lock the lock.                                      | str  | `LOCK` |
| payload_unlock   | Command payload used to unlock the lock.                                    | str  | `UNLOCK` |
| state_locked     | Payload sent to `state_topic` when the lock is locked.                      | str  | `LOCKED` |
| state_locking    | Payload sent to `state_topic` when the lock is locking.                     | str  | `LOCKING` |
| state_unlocked   | Payload sent to `state_topic` when the lock is unlocked.                    | str  | `UNLOCKED` |
| state_unlocking  | Payload sent to `state_topic` when the lock is unlocking.                   | str  | `UNLOCKING` |
| state_jammed     | Payload sent to `state_topic` when the lock is jammed.                      | str  | `JAMMED` |

```json
{
  "component": "lock",
  "optimistic": false,
  "payload_lock": "LOCK",
  "payload_unlock": "UNLOCK",
  "state_locked": "LOCKED",
  "state_locking": "LOCKING",
  "state_unlocked": "UNLOCKED",
  "state_unlocking": "UNLOCKING",
  "state_jammed": "JAMMED",
  "retain": false
}
```

DGB binder run.action.call and (optional) run.action.args:

TODO: make table

[top](#table-of-contents)

#### Number

HMD parameters:

| Parameter            | Description                                                                 | Type        | Default |
|---------------------|-----------------------------------------------------------------------------|-------------|---------|
| component            | One of the supported MQTT components. For this entity, defaults to `number`. | str         | `number` |
| max                  | Maximum value of the number.                                                 | float \| int | `100` |
| min                  | Minimum value of the number.                                                 | float \| int | `1` |
| mode                 | Controls how the number is displayed in the UI. Can be set to `box` or `slider` to force a display mode. | str | optional |
| optimistic           | Flag that defines whether the number entity works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool | optional |
| payload_reset        | Special payload that resets the state to `None` when received on the `state_topic`. | str | optional |
| retain               | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |
| step                 | Step value for the number. Smallest acceptable value is 0.001. Defaults to 1.0 if not set. | float | optional |
| unit_of_measurement  | Defines the unit of measurement of the sensor, if any.                      | str | optional |

```json
{
  "component": "number",
  "min": 1,
  "max": 100,
  "mode": "slider",
  "step": 1.0,
  "unit_of_measurement": "%",
  "optimistic": false,
  "retain": false,
  "payload_reset":  "???"
}

```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| set_value   |   Update the numeric value                            | value  | float |  Value of the number configured for this entity |

[top](#table-of-contents)

#### Select

HMD parameters:

| Parameter   | Description                                                                 | Type | Default |
|------------|-----------------------------------------------------------------------------|------|---------|
| component  | One of the supported MQTT components. For this entity, defaults to `select`. | str  | `select` |
| optimistic | Flag that defines whether the select entity works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool | optional |
| retain     | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |
| options    | List of selectable options. An empty list or a list with a single item is allowed. | list | `[]` |

```json
{
  "component": "select",
  "optimistic": false,
  "options": ["option_a", "option_b", "option_c"],
  "retain": false
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| select_option   |   Update the selected option.                           | option  | str |  The option to be selected. |

[top](#table-of-contents)

#### Sensor

HMD parameters:

| Parameter                     | Description                                                                 | Type | Default |
|------------------------------|-----------------------------------------------------------------------------|------|---------|
| component                    | One of the supported MQTT components. For this sensor, defaults to `sensor`. | str  | `sensor` |
| unit_of_measurement          | Defines the units of measurement of the sensor, if any.                     | str  | optional |
| state_class                  | Defines the type of state. If set, the sensor is assumed to be numerical and will be displayed as a line chart instead of discrete values in the frontend. | str  | optional |
| value_template               | Template used to extract the sensor value. If the template throws an error, the current state is used instead. | str  | optional |
| last_reset_value_template    | Template used to extract `last_reset`. When set, `state_class` must be `total`. Available variables include `entity_id`, which can reference the entity's attributes. | str  | optional |
| suggested_display_precision  | Number of decimals used to round the sensor state. Must be greater than or equal to 0. | int  | optional |

```json
{
  "component": "sensor",
  "unit_of_measurement": "°C",
  "state_class": "measurement",
  "value_template": "???",
  "last_reset_value_template": "???",
  "suggested_display_precision": 1
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| set_state   |  Update the sensor state                           | state  | bytes, str, int or float |  What state to set the sensor to |

[top](#table-of-contents)

#### Switch

HMD parameters:

| Parameter     | Description                                                                 | Type | Default |
|--------------|-----------------------------------------------------------------------------|------|---------|
| component    | One of the supported MQTT components. For this entity, defaults to `switch`. | str  | `switch` |
| optimistic   | Flag that defines whether the switch works in optimistic mode. Default behavior is `true` if no `state_topic` is defined, otherwise `false`. | bool | optional |
| payload_off  | Payload that represents the OFF state. Used both for comparing against the value received on `state_topic` and for sending the OFF command to `command_topic`. | str  | `OFF` |
| payload_on   | Payload that represents the ON state. Used both for comparing against the value received on `state_topic` and for sending the ON command to `command_topic`. | str  | `ON` |
| retain       | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |
| state_topic  | MQTT topic subscribed to receive state updates.                             | str  | optional |

```json
{
  "component": "switch",
  "optimistic": false,
  "payload_on": "ON",
  "payload_off": "OFF",
  "retain": false,
  "state_topic": "example/switch/state"
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| off   | Set switch to off.                                                      |   |  |   |
| on   | Set switch to off.                                                     |   |  |  |

[top](#table-of-contents)

#### Text

HMD parameters:

| Parameter | Description                                                                 | Type | Default |
|----------|-----------------------------------------------------------------------------|------|---------|
| component | One of the supported MQTT components. For this entity, defaults to `text`. | str  | `text` |
| max      | Maximum length of the text being set or received (maximum allowed is 255). | int  | `255` |
| min      | Minimum length of the text being set or received.                           | int  | `0` |
| mode     | Mode of the text entity. Must be either `text` or `password`.               | str  | `text` |
| pattern  | Regular expression that the text being set or received must match.          | str  | optional |
| retain   | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |

```json
{
  "component": "text",
  "max": 255,
  "min": 0,
  "mode": "text",
  "pattern": "???",
  "retain": false
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| set_text   | Update the text displayed by this sensor.                                 | text  | str  |  Value of the text configured for this entity |

[top](#table-of-contents)

#### Valve

HMD parameters:

| Parameter          | Description                                                                 | Type | Default |
|-------------------|-----------------------------------------------------------------------------|------|---------|
| component          | The MQTT component type for this entity.                                    | str  | `valve` |
| optimistic         | Flag that defines whether the valve works in optimistic mode.               | bool | `False` |
| payload_open       | Payload that represents the open command.                                   | str  | `OPEN` |
| payload_close      | Payload that represents the close command.                                  | str  | `CLOSE` |
| payload_stop       | Payload that represents the stop command.                                   | str  | `STOP` |
| position_open      | Numeric value that represents the fully open position.                      | int  | `100` |
| position_closed    | Numeric value that represents the fully closed position.                    | int  | `0` |
| reports_position   | Set to true if the valve reports or supports setting a position.            | bool | `False` |
| state_open         | Payload that represents the open state.                                     | str  | `open` |
| state_opening      | Payload that represents the opening state.                                  | str  | `opening` |
| state_closed       | Payload that represents the closed state.                                   | str  | `closed` |
| state_closing      | Payload that represents the closing state.                                  | str  | `closing` |
| retain             | Defines whether the published MQTT message should have the retain flag set. | bool | `False` |

```json
{
  "component": "valve",
  "optimistic": false,
  "payload_open": "OPEN",
  "payload_close": "CLOSE",
  "payload_stop": "STOP",
  "position_open": 100,
  "position_closed": 0,
  "reports_position": false,
  "state_open": "open",
  "state_opening": "opening",
  "state_closed": "closed",
  "state_closing": "closing",
  "retain": false
}
```

DGB parameters:

| Parameter         | Description                                                                 | Type | Default |
|------------------|-----------------------------------------------------------------------------|------|---------|
| time_based_state        | Valve position is calculated based on the active time | bool  | `False` |
| direct_state_transition  | If True, valve states will change directly based on paload commands, otherwise states must be managed via the binder with run.action.call | bool | `True` |

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|-------|------|-------------|
| open        | Set valve state to open                                                      |          |      |             |   |      |             |
| closed      | Set valve state to closed                                                      |          |      |             |   |      |             |
| closing     | Set valve state to closing                                                      |          |      |             |   |      |             |
| opening     | Set valve state to opening                                                      |          |      |             |   |      |             |
| position     | Set the valve to a desired position between 0 and 100.                         |   position       | int     | position of the valve     |   state (optional)      | str     | state of the valve (as defined in state_open, state_opening, state_closed or state_closing)     |

[top](#table-of-contents)

### Pins with PinInfo

In this section lists the configuration parameters and defaults for GPIO pins. In the background pins are configured and managed by the [GPIOzero](https://github.com/gpiozero/gpiozero) package. HMD-DGB provides an overlay on this package. Most parameters allign with those form [GPIOzero](https://github.com/gpiozero/gpiozero), though al are defined within HMD-DGB and are listed below. Aditionally you find the run.action.call ids and run.action.args that can be used in binding via [Durable Rules](https://github.com/jruizgit/rules).

[top](#table-of-contents)

#### PinIn

DGB parameters:

| Parameter      | Description                                                                 | Type | Default |
|----------------|-----------------------------------------------------------------------------|------|---------|
| pin            | GPIO pin number to configure, change, or read.                              | int  | required |
| ptype          | Functional type of the pin (input).                                         | str  | `pinin` |
| active_state   | If `true`, a HIGH hardware signal maps to HIGH software state. If `false`, the input polarity is inverted. | bool | `True` |
| pull_up        | If `true`, the pin is pulled high using an internal resistor. If `false`, the pin is pulled low. | bool | `True` |
| webhook        | Home Assistant endpoint to send state changes to when they occur.          | str  | optional |

```json
{
  "pin": 17,
  "ptype": "pinin",
  "active_state": true,
  "pull_up": true,
  "webhook": "/api/webhook/gpio_pin_17"
}
```

PinIn has no binder run.action.call and (optional) run.action.args

[top](#table-of-contents)

#### PinOut

DGB parameters:

| Parameter     | Description                                                                 | Type | Default |
|---------------|-----------------------------------------------------------------------------|------|---------|
| pin           | GPIO pin number to configure, change, or control.                           | int  | required |
| ptype         | Functional type of the pin (output).                                        | str  | `pinout` |
| initial       | Initial output value of the pin when it is created.                         | int  | `0` |
| active_state  | If `true`, a HIGH software state maps to a HIGH hardware output. If `false`, the output polarity is inverted. | bool | `False` |
| value         | Desired output value of the pin.                                            | int  | optional |
| password      | Optional safety password to prevent unwanted activation of the pin. **Do not reuse real account passwords** (no HTTPS or encryption). | str | optional |
| blink      | The blink time of the output once for this number of seconds. Note it uses the previous set value to start from, the value of this call will be ignored. | int | optional |

```json
{
  "pin": 27,
  "ptype": "pinout",
  "initial": 0,
  "active_state": false,
  "value": 1,
  "password": "local-control-only",
  "blink": 2
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| on        | Set pin state to on                                                      |          |      |             |
| off      | Set pin state to off                                                      |          |      |             |
| blink      | Set pin state to on for a certain time                                     |    blink      |  int    |      The blink time of the output once for this number of seconds.       |

[top](#table-of-contents)

#### PinCount

DGB parameters:

| Parameter     | Description                                                                 | Type | Default |
|---------------|-----------------------------------------------------------------------------|------|---------|
| pin           | GPIO pin number to configure, change, or read.                              | int  | required |
| ptype         | Functional type of the pin (counting input).                                | str  | `pincount` |
| active_state  | If `true`, a HIGH hardware signal maps to a HIGH software state. If `false`, the input polarity is inverted. | bool | `True` |
| pull_up       | If `true`, the pin is pulled high using an internal resistor. If `false`, the pin is pulled low. | bool | `False` |
| webhook       | Home Assistant endpoint to send count/state changes to when they occur.    | str  | optional |

```json
{
  "pin": 5,
  "ptype": "pincount",
  "active_state": true,
  "pull_up": false,
  "webhook": "/api/webhook/gpio_counter_5"
}
```

PinCount has no binder run.action.call and (optional) run.action.args

[top](#table-of-contents)

#### PinNWayOut

DGB parameters:

| Parameter      | Description                                                                 | Type | Default |
|----------------|-----------------------------------------------------------------------------|------|---------|
| pin            | GPIO pin used to identify the n‑way output configuration. This pin must also be present in `pin_list`. | int | required |
| pin_list       | List of **≥ 2** GPIO pins controlled by this n‑way output. May include “dummy” pins indicated by `-1`. The `pin` must be included in this list. | list[int] | required |
| ptype          | Functional type of the pin (n‑way output).                                  | str | `pinnwayout` |
| initial        | Initial output values for each pin. Order must match `pin_list`. At most one pin may be HIGH; this may also be a dummy pin. | list[int] | `[0]` |
| active_state   | List defining output polarity per pin. Order must match `pin_list`. If `true`, HIGH software state maps to HIGH hardware state; otherwise output is inverted. | list[bool] | `[False]` |
| pin_names      | Human‑readable names for each pin. Order must match `pin_list`. Examples: `["open", "close", "stop"]` or `["0", "1", "2"]`. | list[str] | `[""]` |
| active_pin     | Pin to activate, specified either by pin number (`int`) or by `pin_names` entry (`str`). Set to `-1` to deactivate all pins. | int \| str | optional |
| password       | Optional safety password to prevent unwanted activation. Applies to all pins but is only checked for the first pin in `pin_list`. **Do not reuse real passwords** (no HTTPS or encryption). | str | optional |

```json
{
  "pin": 22,
  "pin_list": [22, 23, 24],
  "ptype": "pinnwayout",
  "initial": [0, 0, 0],
  "active_state": [false, false, false],
  "pin_names": ["open", "close", "stop"],
  "active_pin": "open",
  "password": "local-control-only"
}
```

DGB binder run.action.call and (optional) run.action.args:

| Call name    | Description                                                                 | Argument | Type | Description |
|-------------|------------------------------------------------------------------------------|----------|------|-------------|
| on        | Set pin state to on                                                      |    active_pin      |  int    |     The GPIO pin id to turn on        |
| off      | Set pin state to off                                                      |          |      |             |
<!-- | blink      | Set pin state to on for a certain time                                     |          |      |             |   |      |             | -->

[top](#table-of-contents)

### Bindings with BindInfo

The binder manages actions to execute on specific device (entitie) and pin triggers via binding rules. These rules are loaded in [Durable Rules](https://github.com/jruizgit/rules) and follow mostly the rich [JSON](https://github.com/jruizgit/rules/blob/master/docs/json/reference.md) schema documentation. Some basics are shown here, but details and examples can be found at the [JSON documentation](https://github.com/jruizgit/rules/blob/master/docs/json/reference.md). Note that multiple implementations of rulesets can acomplisch the same thing, though still it may be good to use copilot or another AI tool to generate a fisrt draft for you.

Next to the basis, these sections show the HMD-DGB addition/changes to the JSON schema. These changes/aditions are limited to the sublabels of the run label, but also impose limitations to the other parts of the schema. This will be explained in detail in the designated sections. Additional to the documentation here, I made several tests to check de binder stand-alone in [Binder_examples.py](https://github.com/jvanoosterhout/HMD-DGB/blob/main/Examples/Binder_examples.py).

[top](#table-of-contents)

#### Ruleset

Durable Rules allow a few different ways to organize a ruleset, plus a fairly rich set of matching constructs inside a rule. The main categories are:
- plain rulesets
- statecharts (requires $state identifier)
- flowcharts (requires $flow identifier)

These catagories support for events, state events, correlated sequences, negative conditions, nested objects/arrays, and priorities. Timers are normally also supported, though not via JSON, theref DGB has iets own timer construct on top of Durable Rules. The catagories normally also support facts, though DGB has no implementation for facts at this moment.

In general you define a ruleset like this:

```JSON
binding_info =  {
                  "my_plain_ruleset": { ... }
                }

binding_info =  {
                  "my_statechart$state": { ... }
                }

binding_info =  {
                  "my_flowchart$flow": { ... }
                }
```

[top](#table-of-contents)

#### Rule conditions

A **plain ruleset** can have multiple rules/condition with antecedent. Durable Rules has two main antecedent: all and any. These can be combined and nested to express richer patterns. The antecedent can have a:
- Single message pattern with the 'm' label. All clauses from one event must match to fire the rule.
- Named correlated pattern (first, second, …). The individual named patterns must match in one message to be true, but the rule only fires if all named patterns match.
- Nested branch inside all or any.

A simple example of a plain ruleset:
```JSON
{
  "my_plain_ruleset": {
    "r_0": {
      "all": [
        { "m": [{"unique_id": "x"}, {"payload": "y"}] }
      ],
      "run": {...}
    }
    "r_1": {
      "all": [
        {"first": {"unique_id": "x", "payload": "y"}},
        {"second": {"unique_id": "u", "payload": "v"}},
      ],
      "run": {...}
    }
    "r_2": {
      "any": [
        { "m": [{"unique_id": "x"}, {"$lt": {"payload": 1}}] },
        { "m": {"timeout": "z"} }
      ],
      "run": {...}
    }
  }
}
```

A **Statechart** is best defined by [Durable Rules](https://github.com/jruizgit/rules/blob/master/docs/json/reference.md) them selfs:

> Rules can be organized using statecharts. A statechart is a deterministic finite automaton (DFA). The state context is in one of a number of possible states with conditional transitions between these states.
>
> Statechart rules:
>
> - A statechart can have one or more states.
> - A statechart requires an initial state.
> - An initial state is defined as a vertex without incoming edges.
> - A state can have zero or more triggers.
> - A state can have zero or more states (see nested states).
> - A trigger has a destination state.
> - A trigger can have a rule (absence means state enter).
> - A trigger can have an action.

For a binding, statecharts are especially useful when an actor/device has lifecycle states, for example:

- idle
- pending
- active
- timed_out
- error

Then transitions can be driven by:

- a specific unique_id,
- a payload,
- a timeout/timer signal

This is likely cleaner than plain correlated rules if your logic depends on where the actor currently is in a lifecycle.

A simple example of a statechart:
```JSON
{
    "my_statechart$state": {
        "start": {"t_0": {"to": "waiting"}},
        "waiting": {
            "on": {
                "all": [...],
                "to": "got_on",
                "run": {...},
            },
        },
        "got_on": {
            "temp_timeout": {
                "all": [...],
                "to": "waiting",
                "run": {...},
            },
        },
    }
}
```

A **flowcharts** is best defined by [Durable Rules](https://github.com/jruizgit/rules/blob/master/docs/json/reference.md) them selfs:
> A flowchart is another way of organizing a ruleset flow. In a flowchart each stage represents an action to be executed. So (unlike the statechart state), when applied to the context state, it results in a transition to another stage.
>
> Flowchart rules:
>
> - A flowchart can have one or more stages.
> - A flowchart requires an initial stage.
> - An initial stage is defined as a vertex without incoming edges.
> - A stage can have an action.
> - A stage can have zero or more conditions.
> - A condition has a rule and a destination stage.

For a binding, a flowchart is a better fit (compaired to Statechart) when the logic is more like a process pipeline than a persistent actor state machine. Example shape:

- input
- validate
- wait_for_payload
- timeout_or_accept
- finalize

So:
- Statechart = “what state is this actor/device in?”
- Flowchart = “what processing stage is this event/work item in?”

A simple example of a flowchart:
```JSON
{
  "my_flowcharts$flow": {
    "input": {
      "to": {
        "request_on": {
          "all": [...]
        },
        "off": {
          "all": [...]
        }
      }
    },
    "request_on": {
      "run": "log_request_on",
      "to": {
        "on": {
          "all": [...]
        },
        "off": {
          "all": [...]
        },
        "request_on": {
          "all": [...]
        }
      }
    },
    "on": {
      "run": "log_on",
      "to": {}
    },
    "off": {
      "run": "log_off_",
      "to": {}
    }
  }
}
```

As shown in the first example in this section, the matching constructs inside the rule is in JSON format. Each key-value pair presents a match patren, e.g.: {"unique_id": "x"}, {"payload": "y"} means Unique_id = "x" and payload = "y". Though many matching constructs are posible. A few of them are:
- Logical operators likr negative / absence pattern ($not), or ($or), and ($and), exists ($ex), not exist ($nex),
- Relational operators like, less than ($lt), greater than ($gt), less than or equal ($lte), greater than or equal ($gte), not equal ($neq)
- Patrens like match pattern ($mt) and case-insensitive match pattern ($imt)
- Arithmetic expressions like $add, $sub, $mul, $div

HMD-DGB currently only support posting one entity/pin/timer message in the shape of an event, meaning that they are an ephemeral: they are evaluated and then gone. The posts have the shape of:

```JSON
{"unique_id": "...", "payload": "..."}
{"timeout": "..."}
```

[top](#table-of-contents)

#### Rule run actions

Forget the JSON run option in the [JSON documentation](https://github.com/jruizgit/rules/blob/master/docs/json/reference.md), they won't work. Even the times do not work.

HMD-DGB provides a custom overlay to run action. These actions are:
- log a message to the logger
- start/stop a timer
- run an action of an entity/pin (i.e. call a function of the device, args are optional)

One run label can call multiple action by putting them in a array where they will be executed in order:
```JSON
{
  "my_plain_ruleset": {
    "r_0": {
      "all": [...],
      "run": [
          {"log": {"msg": "x"}},
          {"log": {"msg": "y"}},
        ],
    }
  }
}
```

[top](#table-of-contents)

##### Log
The most simple run action: set the "log" key. Its value is a dict containing the key value pair "msg" and the "the message you want to be displayed". This is most valuable for debugging purposes.
```JSON
{
  "my_plain_ruleset": {
    "r_0": {
      "all": [...],
      "run": [{"log": {"msg": "x"}}],
    }
  }
}
```

[top](#table-of-contents)

##### timer

Timers can be used to schedule an event at timeout. To use this event, a timeout condition can be included in the rule antecedent. Each timer runs in a separate thread. Timers are thuse non-blocking.

Timers can be set by the "timer" key. Its value is a dict containing:
- name: the name of the timer, this name is used to start and cancel it in run, but also to wait for the timeout in an rule antecedent.
- action: the action to perform on the timer, which can be either "start" or "cancel". If a timeout has not occured yet, "cancel" will delete the timer identified by name, if it exists. The timeout event will never hapen. If a timer is started, and not timeout yet, "start" will cancel the existing timer with identical name and create a new one.
- seconds: define the number of seconds the timer last before timeout. Only required for action "start".

Timeouts can be set in a rule antecedent by using the key "timeout" with value the name of the timer that should fire the rule.

```JSON
{
  "my_plain_ruleset": {
    "r_0": {
      "all": [...],
      "run": [{"timer": {"name": "x", "action": "start", "seconds": 1}}],
    }
    "r_1": {
      "all": [
        { "m": [{"timeout": "x"}] }
      ],
      "run": {...}
    }
  }
}
```

[top](#table-of-contents)

##### action

Actions can be used to set the state of an entity or pin via one of the device function. This is usefull to bind an entity action (e.g. a button press in HA) to activate a pin (e.g. set pinout to high). But also the other way around is meaningfull: when a pin is high (e.g. PinIn is 1) do something with an entity state (e.g. set a binary sensor in HA to on).

Actions can be set by the "action" key. Its value is a dict containing:
- unique_id:
- call:
- args:
  - name:
  - value: "$m.payload"

The call functions and args (with name and value) can be found in [Devices with EntityInfo](README.md#devices-with-entityInfo) and [Pins with PinInfo](README.md#pins-with-pinInfo).

```JSON
{"action": {"unique_id": "y", "call": "z", "args": [{"name": "var1", "value": "$m.payload"}]}}
```

```JSON
{
  "delayed_action": {
      "p_on": {
          "all": [{"m": {"$and": [{"unique_id": "s4"}, {"payload": "on"}]}}],
          "run": [
              {"timer": {"name": "auto_off", "action": "start", "seconds": 3}},
              {"action": {"unique_id": "p1", "call": "on"}},
              {"log": {"msg": "p1 is set to on"}},
          ],
      },
      "timeout": {
          "all": [{"m": {"timeout": "auto_off"}}],
          "run": [
              {"action": {"unique_id": "p1", "call": "off"}},
              {"log": {"msg": "p1 is set to off"}}
          ],
      },
  }
}
```

[top](#table-of-contents)

## Architecture

```
┌───────────────────────────────┐
│    Home Assistant             │
│  (with MQTT integration)      │
├───────────────────────────────┤
│     MQTT Broker               │
│    (Mosquitto/etc)            │
└───────────────────────────────┘
               ↑
               │ MQTT Messages
               ↓
┌───────────────────────────────┐
│  HMD-DGB MQTT                 │
│  (configuration management    │
│   on Raspberry Pi)            │
├───────────────────────────────┤
│ DeviceKeeper (HMD package)    │
│ Binder (Durable Rules package)│
│ PinKeeper (GPIOzero package)  │
└───────────────────────────────┘
               ↑
               │ GPIO Signals
               ↓
┌───────────────────────────────┐
│  Physical GPIO Pins           │
│  Connected Devices            │
│  (Relays, Sensors, etc)       │
└───────────────────────────────┘
```

[top](#table-of-contents)

## Ideas for improvement (unsorted in priority)

- Triggering payload as argument in action
  - <del>Add support to use the payload of the triggering device as argument in the action function</del>
  - Match best type of arg for multi type function args (naow: payload = int & function accepts str|int|bool --> convert int to str; should be pass int)
  - Make it posible to define case type in configuration (e.g. "value": "$m.payload|int")
  - <del>Provide readmeon posible arg names and types per fuction
- Improve run actions</del>
  - Provide log feedback on posible arg names and types per fuction
- Improve run actions
  - <del>create readme documentation on the posible actions (log, action, timer, ...)</del>
  - Extend run action with the option to perform a post to a ruleset with specific context
- Improve device, GPIO and binder configuration
  - Add key to define prefered (re)start state (previous known in HA, or user defined state)
  - Make configuration possible from yaml
  - Allow to delete objects:
    - device (incl ha entitys by cleaning up topics)
    - rules
    - gpio pins
- Improve systems capabilities and robustness
  - <del>Make system sensors configurable</del>
  - Add RPI device action (e.g. <del>restart</del>, update, reload, ...)
  - Add log messages over MQTT in RPI device
  - Splitt loading and active phase: prevent post from being evaluated while rules may not be in place (e.g. set a system flag: loading = true while new mqtt config messages are being  processed)
  - Make pytest for all files.
- Improve GPIO (custom or an available package)
  - Count-type pins: Finalization for water flow meters and pulse counters
  - Time-series I/O: RF signal handling for advanced sensor integration
  - PWM support: LED brightness and voltage regulation control
  - Replace gpio module for use on diffferent single board coputers (e.g. Mqtt-io, Adafruit Blinka, Libgpio)
- Improve system setup:
  - <del>Make example with arg configuration of system name, mqtt and some other system settings (acount for secure passwords)</del>
  - [Won't for now: pi zero has no hardware to store secretes truely safe for an automatic system like HMD-DGB] <del>Potentially include a local webserver to set wifi and mqtt credentials and store them encrypted</del>
  - Docker deployment: Streamlined container-based setup with pre-configured environment
  - Define cloud-init (e.g. for Trixi) or simmilar script to configure a pi at first boot
  - (external project) Make tool to write Device, GPIO and Binder configurations (host on local webserver)
- Improve Devices
  - <del>Support more HMD device (focus on valve)</del>
  - Implement time based cover/valve
  - Implement (distinguish and document) Device configuration specific to HMD-DGB
    - time_based_state (for cover & valve)
    - <del>direct_state_transition (for all devices with callback: acknowlegde state to HA directly or via binding action)</del>

[top](#table-of-contents)

## Known Issues & Limitations

### First load issue

**Status:** Needs Testing

Currently it seems that alle entities are unavailable at the very first creation of xthe discoverable topic, eventough the code explicitly sets them to "available". A soft restart (which button is also unavailable) or similar fixes the issue.

### Loading configurations & runtime

**Status:** Needs Testing

For run.action.args the value of "$m.payload" currently only works if the rule has one payload of one device's unique_id.

### restart of the system

**Status:** Needs Testing

What would currently happen, and should happen when the HMD-DGB service restarts (or the system reboots). Whatever happens, should states be stored and restored, set to unknown, or set to default values?

### Loading configurations & runtime

**Status:** Needs split of operational phases or robust error handling

Currently devices and pins can emit posts directly after creation, rules/bindings can only be set once all included devices and pins are defind --> early posts fail.

### Count-Type Pin Device

**Status:** Not fully functional

Currently the count-type pin implementation is incomplete. Water flow meters and other pulse-based sensors may not work reliably. This is targeted for completion in an upcoming release.

### Maintenance/updates of Durable Rules

**Status:** unknown

Durable Rules has limited maintenance/updates and no reponces on issues lately. It is unclear how well or how long this package will be able to keep up with updates of other packages.

[top](#table-of-contents)

## Contributing

This is a **spare-time project**, so feedback and suggestions are highly appreciated!

**Current approach:**
- Open issues for bugs or feature requests with detailed descriptions

**What helps most:**
- Bug reports with reproduction steps
- Feature requests with real-world use cases
- Documentation improvements and examples
- Testing on different hardware configurations

[top](#table-of-contents)

## Project Status

This is the first public iteration of the HMD-DGB project, transitioning from private development to community use. Expect:
- Ongoing improvements to core functionality
- API refinements and potential breaking changes
- Expanded documentation and examples
- Bug fixes and stability improvements

---

**Questions or ideas?** Open an issue on GitHub and let's improve HMD-DGB together!

**Found this project helpful?** Consider starring it on GitHub or sharing it with others!

[top](#table-of-contents)
