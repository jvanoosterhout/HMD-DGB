# HMD-DGB: Home Assistant MQTT-Discoverable Device GPIO Binder

Control Raspberry Pi GPIO pins via MQTT with automatic Home Assistant discoverable devices. Bridge your custom hardware to smart home automation through declarative device bindings via durable rules.

## Overview

**HMD-DGB** (Home Assistant MQTT-Discoverable Device GPIO Binder) provides a Python-based solution for managing GPIO pins on Raspberry Pi with Home Assistant integration via MQTT discoverable devices. Unique to this package is that it is an end-to-end solution reling on the [ha-mqtt-discoverable](https://github.com/unixorn/ha-mqtt-discoverable) package for MQTT Discovery and [Durable Rules](https://github.com/jruizgit/rules) to bind these devices to [GPIOzero](https://github.com/gpiozero/gpiozero) pins . This eliminats manual programing via easy configuration. While developping this package over the years, I learned that this resembles several aspects of ESP Home.

The system consists of four core concepts:

- **MQTT Discoverable Devices**: Devices that automatically appear in Home Assistant via MQTT discovery protocol
- **Durable Binding Rules**: Define relationships and actions between physical GPIO pins and Home Assistant devices
- **GPIOzero Devices**: configuration of GPIO pins to proform meaningfull action in the real world
- **on the fly configuration**: send device, binding and GPIO configurations over MQTT to your Raspberry Pi (you still need to install this package, configure HA, and setup a service)

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

- **Python**: 3.10.0 or higher
  - Required for Pydantic v2 compatibility (only used for fastapi legacy implementation)
  - Tested on Python 3.10.0 and 3.11.2

- **MQTT Broker**: Mosquitto or compatible
  - Can be local or remote
  - Required for device communication

- **Home Assistant**: 2023.1 or later
  - MQTT integration/addon required
  - For automatic device discovery

### Tested Platforms

- Raspberry Pi 4 with Bookworm (64-bit, desktop) and Python 3.11.2
- Raspberry Pi Zero 2 W with Bookworm (32-bit, lite) and Python 3.10.0

## Installation

### Option 1: Quick Start (Install from Git)

```bash
# Create project directory and virtual environment
mkdir hmd-dgb-project && cd hmd-dgb-project
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
# Install from repository
pip install git+https://github.com/jvanoosterhout/HMD-DGB.git
```

### Option 2: Using Provided Setup Scripts

```bash
# Install from repository
mkdir hmd-dgb-project && cd hmd-dgb-project
git clone https://github.com/jvanoosterhout/HMD-DGB.git
cp -r HMD-DGB/Examples ./
cd Examples/[your_example_of_choise]
# edit the .._example.py file and run the venv creation and service creation script
./install_venv.sh
./install_service.sh
# View service logs
journalctl -u hmd-dgb -f
```

### Option 3: instal from project folder
```bash
mkdir hmd-dgb-project && cd hmd-dgb-project
git clone https://github.com/jvanoosterhout/HMD-DGB.git
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
pip install -e HMD-DGB  #  -e is optional to install the package in editable mode

```

### Option 4: Docker

Docker support is on the roadmap simplified deployment and consistency across systems.


## Quick Start

### Basic Configuration

TODO

**Behavior:**
- Click → Opening → Wait → Fully opened → Click → Closing → Wait → Fully closed
- Click → Opening → Click → Stop (somewhere in between) → Click → Closing

**Hardware Notes:**
- May require a relay board to isolate Pi and door/gate electric circuits
- Magnetic reed switches recommended for position detection
- Ensure proper voltage protection for connected devices

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

## Usage

### API Documentation (legacy fastapi implementation)

If REST endpoints are available, access the interactive documentation at:

```
http://<pi-ip>:11411/docs
```

This provides:
- View of all available endpoints
- Ability to test API calls directly
- Request/response schema documentation

### MQTT Topics

HMD-DGB publishes and subscribes to the following MQTT topics:

- the default homeassistant discoverable topics (publishe and subscribe)
- the "config/[RPI-name]/devices/[sub-topic]" topic (subscribe) to recieve configurations for devices, bindings and GPIO.

## Ideas for improvement (unsorted in priority) 

- Triggering payload as argument in action
  - <del>Add support to use the payload of the triggering device as argument in the action function</del>
  - Match best type of arg for multi type function args (naow: payload = int & function accepts str|int|bool --> convert int to str; should be pass int)
  - Make it posible to define case type in configuration (e.g. "value": "$m.payload|int")
  - Provide readme / log feedback on posible arg names and types per fuction
- Improve run actions
  - create readme documentation on the posible actions (log, action, timer, ...)
  - Extend run action with the option to perform a post to a ruleset with specific context 
- Improve device, GPIO and binder configuration
  - Make configuration possible from yaml
  - Allow to delete objects:
    - device (incl ha entitys by cleaning up topics)
    - rules 
    - gpio pins
- Improve systems capabilities and robustness
  - Make system sensors configurable
  - Add RPI device action (e.g. restart, update, reload, ...)
  - Add log messages over MQTT in RPI device
  - Splitt loading and active phase: prevent post from being evaluated while rules may not be in place (e.g. set a system flag: loading = true while new mqtt config messages are being  processed)
  - Make pytest for all files.
- Improve GPIO (custom or an available package)
  - Count-type pins: Finalization for water flow meters and pulse counters
  - Time-series I/O: RF signal handling for advanced sensor integration
  - PWM support: LED brightness and voltage regulation control
  - Replace gpio module for use on diffferent single board coputers (e.g. Mqtt-io, Adafruit Blinka, Libgpio)
- Improve system setup:
  - Make example with arg configuration of system name, mqtt and some other system settings (acount for secure passwords)
    - Potentially include a local webserver to set wifi and mqtt credentials and store them encrypted 
  - Docker deployment: Streamlined container-based setup with pre-configured environment
  - Define cloud-init (e.g. for Trixi)
  - (external project) Make tool to write Device, GPIO and Binder configurations (host on local webserver)
- Improve Devices
  - Support more HMD device (focus on valve)
  - Implement time based cover/valve
  - Implement (distinguish and document) Device configuration specific to HMD-DGB
    - time_based_state (for cover & valve)
    - direct_state_transition (for all devices with callback: acknowlegde state to HA directly or via binding action)

## Known Issues & Limitations

### Loading configurations & runtime

**Status:** Needs split of operational phases or robust error handling

Currently devices and pins can emit posts directly after creation, rules/bindings can only be set once all included devices and pins are defind --> early posts fail. 


### Count-Type Pin Device

**Status:** Not fully functional

Currently the count-type pin implementation is incomplete. Water flow meters and other pulse-based sensors may not work reliably. This is targeted for completion in an upcoming release.

### Home Assistant Offline During Webhook Update

**Status:** Needs Testing

The behavior when Home Assistant is offline while HMD-DGB attempts to send webhook updates is not fully tested. You may experience state synchronization issues. Consider this for critical automations.

## Contributing

This is a **spare-time project**, so feedback and suggestions are highly appreciated!

**Current approach:**
- Open issues for bugs or feature requests with detailed descriptions

**What helps most:**
- Bug reports with reproduction steps
- Feature requests with real-world use cases
- Documentation improvements and examples
- Testing on different hardware configurations

## License

MIT License - See LICENSE file in the repository for full details.

This license allows:
- Commercial and private use
- Modification and distribution
- Use with warranty disclaimer

## Project Status

**v0.1 (Develop Branch)** - Active Development

This is the first public iteration of the HMD-DGB project, transitioning from private development to community use. Expect:
- Ongoing improvements to core functionality
- API refinements and potential breaking changes
- Expanded documentation and examples
- Bug fixes and stability improvements

---

**Questions or ideas?** Open an issue on GitHub and let's improve HMD-DGB together!

**Found this project helpful?** Consider starring it on GitHub or sharing it with others!
