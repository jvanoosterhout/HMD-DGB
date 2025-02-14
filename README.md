# GPIOpinAPI

## Overview
GPIOpinAPI is a Python package designed to simplify the interaction with GPIO pins on a **Raspberry Pi** from another system (specifically Home Assistant, though not limited to it) via REST calls. 
It provides an easy-to-use API for configuring, reading, and writing to GPIO pins, making it ideal for **domotics** and IoT projects. A special feature is to provide a Home Assistant webhook in the configuration of input-type pins.

## Features
* **Easy Configuration**: Quickly set up GPIO pins with simple REST commands.
* **Read/Write Operations**: Perform read and write operations on GPIO pins.
* **Local Push Updates**: Send a webhook update to Home Assistant when an input device-type pin is (de)activated.
* **Persistent Connectivity**: The connectivity survives a reboot of either the Pi or the Home Assistant system, due to the requirement of sending the essential pin details with every call.
* **Swagger UI Docs**: Check and test the API capabilities.

## Installation 

Tested on **Raspberry Pi 4 and Zero** with **Bookworm (64-bit)**.

### Run it yourself 

* Clone the project to your system 
* Create a project folder
* Create and activate a **venv** in the project folder. 
   ``` 
    sudo apt -y install python3-venv
    python3 -m venv venv
    . venv/bin/activate
    ```
* Install the package via ```pip install -e [path-to-the-gpiopinapi-folder]```. (Note: -e is optional to install the package in editable mode)
* Copy or adapt the **/gpiopinapi/Examples/API_example.py** file in your project folder and change the Home Assistant **IP address** and token. Optionally add or remove the pin password list.
* Run the **API_example.py**.
* Check **http://{[the-pi-ip-address]}:11411/docs**.

### Use the venv Example

* Clone the project (or just the **/gpiopinapi/Examples/venv_project** folder).
* Change the Home Assistant **IP address** and token in **/gpiopinapi/Examples/venv_project/API_example.py**.
* Optionally add or remove the pin password list in the **API_example.py**.
* Run the **install_venv.sh**.
* Run the **install_service.sh**.
* Check **http://{[the-pi-ip-address]}:11411/docs**.

### Use Docker

* **TODO**

## Usage

You can test the API most **easily** via **http://{[the-pi-ip-address]}:11411/docs**. The documentation and examples may seem somewhat confusing for the **POST and GET pin** endpoints, though schemas are shown at the **bottom** of the page.

When **integrating** with Home Assistant, you may like the two samples below. **These** samples can be placed in **/homeassistant/configuration.yaml** or in a separate **.yaml** file in the "packages" directory, which you include in the **configuration.yaml** via e.g.:
```
homeassistant:
  packages: !include_dir_merge_named packages/
```

The first sample is a very simple out-put-in-put test where you may want to connect pin gpio21 and gpio20. The first two binnary sensor privide a simple check wether the raspberry is online and running. in case those are not on, the remainder of the test is not representative. When both are on, than as soon as you activate the rpi_pin_out_test swith, the rpi_pin_in_test will be active to (ofcource, when you disconnect the pins, notting will happen).


```
command_line:
    - binary_sensor: 
        name: "rpi_ping_check"
        unique_id: rpi_ping_check
        command: ping -c 1 192.168.70.20 | grep "1 packets received" | wc -l
        device_class: connectivity
        payload_on: 1
        payload_off: 0
        scan_interval: 300
        
sensor:
  - platform: rest
    resource: http://192.168.70.20:11411/api/v1/sys/info
    method: GET
    name: "rpi_sys_info"
    unique_id: rpi_sys_info
    value_template: '{{ value_json.is_active }}'
    json_attributes:
        - cpu_temp
        - up_time
        - cpu_percentage
        - memory_usage
    scan_interval: 300
        
template:
    - trigger:
      - platform: webhook
        webhook_id: pin_in_test
        local_only: true
    binary_sensor:
      - name: "rpi_pin_in_test"
        unique_id: rpi_pin_in_test
        state: "{{ trigger.json.pin_in_test }}"        
        
switch:
  - platform: rest
    name: "rpi_pin_out_test"
    unique_id: rpi_pin_out_test
    resource: http://192.168.70.20:11411/api/v1/pin/out
    method: POST
    state_resource: http://192.168.70.20:11411/api/v1/pin/out?pin=21&initial=0&active_state=0
    body_on: '{"pin": 21, "initial": 0, "value": 1, "active_state": 0}'
    body_off: '{"pin": 21, "initial": 0, "value": 0, "active_state": 0}'
    headers:
        Content-Type: application/json
    is_on_template: '{{ value_json.is_active }}'
    scan_interval: 60
            
rest_command:
    send_rpi_sensors:
    url: http://192.168.70.20:11411/api/v1/pin/in
    method: POST
    headers:
        accept: "application/json"
    content_type: 'application/json'
    payload: '{{pin_in_sensor}}'

automation:
  - id: "send_sensors"
    alias: send_sensors
    description: 'send webhook sensors'
    trigger:
      - platform: state
        entity_id:
            - binary_sensor.rpi_ping_check
            - binary_sensor.rpi_sys_info
      - platform: time_pattern
        minutes: "/10"
    condition: 
    - condition: template
        value_template: "{{ states('binary_sensor.rpi_sys_info')  == 'on'  }}"
    action:
      - service: rest_command.send_rpi_sensors
        data:
            pin_in_sensor: '{"pin": 20, "pull_up": 1, "webhook": "pin_in_test" }'
```

The second sample is for a gate or garage door. Activating your door with a slight touch while you are not near the gate/door, or while your child plays with your phone, seems tricky. Therefore, the "password" comes in handy. It is just a simple double-check to ensure you really want to open the gate/door. 

In this specific example, my garage door is pulse-triggered. The same pulse is used to open, close, or stop the door. This means you can have scenarios like:
* Click --> opening --> wait --> fully opened --> click --> closing --> wait --> fully closed
* Click --> opening --> click --> stop (somewhere while opening) --> click --> closing

For your own gate, you may be able to set different pins for the open, close, and/or stop actions.

Note that the example below and a Pi alone do not suffice; you may need a relay board to isolate the electric circuits of the Pi and the gate/door. Additionally you may need magnetic reed switchs to detect the gate/door is opened/closed. 



```
  input_text:
      gate_pw:
          name: password of the gate
          initial: ""
          icon: mdi:key-chain-variant

  template:  
    - trigger:
        - platform: webhook
          webhook_id: gate_is_open_sensor
          local_only: true
      binary_sensor:
        - name: "gate_is_open"
          unique_id: gate_is_open
          state: "{{ trigger.json.gate_is_open_sensor }}"
          device_class: garage_door
    - trigger:
        - platform: webhook
          webhook_id: gate_is_closed_sensor
          local_only: true
      binary_sensor:
        - name: "gate_is_closed"
          unique_id: gate_is_closed
          state: "{{ trigger.json.gate_is_closed_sensor }}"
          device_class: garage_door            
      
  rest_command:
    send_gate_sensors:
      url: http://192.168.70.20:11411/api/v1/pin/in
      method: POST
      headers:
          accept: "application/json"
      content_type: 'application/json'
      payload: '{{pin_in_sensor}}'
    g_roldeur_bedienen:
    trigger_gate_motor:
      url: http://192.168.70.20:11411/api/v1/pin/in
      method: POST
      headers:
          accept: "application/json"
      content_type: 'application/json'
      payload: '{"pin": 21, "initial": 0, "active_state": 0, "password": "{{ states("input_text.gate_pw")}}", "blink": 1}'

  automation:
    - id: "g_zend_sensoren"
      alias: g_zend_sensoren
      description: 'g zend sensoren'
      trigger:
        - platform: state
          entity_id:
              - binary_sensor.rpi_ping_check
              - binary_sensor.rpi_sys_info
        - platform: time_pattern
          minutes: "/10"
      condition: 
      - condition: template
        value_template: "{{ states('binary_sensor.rpi_sys_info')  == 'on'  }}"
      action:
        - service: rest_command.send_gate_sensors
          data:
              pin_in_sensor: '{"pin": 20, "pull_up": 1, "webhook": "gate_is_open_sensor" }'
        - delay:
              hours: 0
              minutes: 0
              seconds: 10
              milliseconds: 0
        - service: rest_command.send_gate_sensors
          data:
              pin_in_sensor: '{"pin": 16, "pull_up": 1, "webhook": "gate_is_closed_sensor" }'
      mode: single
      
    - id: "trigger_gate"
      alias: trigger_gate
      trigger:
        - platform: device
          device_id: c5c3bcbbff9db90e8a1bbe0fvadfvf
          domain: bthome
          type: button
          subtype: press
          id: "btn 1"
      action:
        - if:
            - condition: trigger
              id: "btn 1"
          then:
            - service: input_text.set_value
              target:
                  entity_id: input_text.gate_pw
              data:
                  value: "ok"
        - service: cover.toggle
          target:
            entity_id: cover.gate
        - service: input_text.set_value
          target:
              entity_id: input_text.gate_pw
          data:
              value: ""
      mode: single
      
  cover:
    - platform: template
      covers:
        gate:
          device_class: "garage"
          friendly_name: "Rol deur garage"
          unique_id: "g_rol_deur"
          open_cover:
            - service: rest_command.trigger_gate_motor
            - service: input_text.set_value
              target:
                  entity_id: input_text.gate_pw
              data:
                  value: ""              
          close_cover:
            - service: rest_command.trigger_gate_motor
            - service: input_text.set_value
              target:
                  entity_id: input_text.gate_pw
              data:
                  value: ""              
          stop_cover:
            - service: rest_command.trigger_gate_motor
            - service: input_text.set_value
              target:
                  entity_id: input_text.gate_pw
              data:
                  value: ""
          availability_template: >-
            {% if is_state('binary_sensor.rpi_sys_info', 'on') %}
              true
            {% else %}
              false
            {% endif %}
          value_template: >-
            {% if is_state('binary_sensor.gate_is_open', 'on') %}
              open
            {% elif is_state('binary_sensor.gate_is_closed', 'off') %}
              closed
            {% elif as_timestamp(states.binary_sensor.gate_is_closed.last_changed) > as_timestamp(states.binary_sensor.gate_is_open.last_changed) %}
              opening
            {% elif as_timestamp(states.binary_sensor.gate_is_open.last_changed) > as_timestamp(states.binary_sensor.gate_is_closed.last_changed) %}
              closing
            {% else %}
              unknown
            {% endif %}
          icon_template: >-
            {% if is_state('binary_sensor.gate_is_open', 'on') %}
              mdi:garage-open
            {% elif is_state('binary_sensor.gate_is_closed', 'off') %}
              mdi:garage
            {% elif as_timestamp(states.binary_sensor.gate_is_closed.last_changed) > as_timestamp(states.binary_sensor.gate_is_open.last_changed) %}
              mdi:arrow-up-bold-box-outline
            {% elif as_timestamp(states.binary_sensor.gate_is_open.last_changed) > as_timestamp(states.binary_sensor.gate_is_closed.last_changed) %}
              mdi:arrow-down-bold-box-outline
            {% else %}
              mdi:garage-alert
            {% endif %}
          
```

## Support
Please feel free to post issues or questions on GitLab. However, please note that this is a spare-time project.

## Roadmap

[test](https://nos.nl/)

* **Finalize count type pin**: Use-case is a water flow meter which generates pulses based on the flow rate, similar to [the one in this link](https://www.otronic.nl/nl/water-flow-sensor.html).
* **Add a time-series-out type pin**: Use-case is to feed an RF transmitter similar to [the one in this link](https://www.otronic.nl/nl/433mhz-rf-zender-en-ontvanger-140567829.html) to send signals to an RF IR panel (in my case, the non-WiFi version of [the one in this link](https://www.gaslooswonen.nl/qh-hl-serie-wifi-infraroodpaneel-met-led-145578285.html)). An older non-public version of GPIOpinAPI is already able to send hardcoded signals.
* **Add a time-series-in type pin**: Use-case is to read RF signals. Processing and extracting the functional part of a time-series RF signal may not be possible within the API.
* **Make webhook useage optional**: Currently a Home Assistant endpoint is required, though this should not be necessary, even better would be the possibility to use another endpoint.
* **Add Docker setup**: Use-case is to make this package more robust to the ever-changing versions of systems and software.
* **Extend pin capabilities**: Add support for input pin devices to trigger only on `when_activated` or `when_deactivated`.
* **Improve the Swagger UI docs**: The docs currently provide a basic, though confusing, overview. For example, the example payload of a POST does not change when the `pin_type` is changed. Also, all query parameters are shown for all pin types.

## Considerations (Why another GPIO package?)

* Many simple automations require expensive commercial and vendor-specific hubs/gateways, while they only need to toggle a switch or read some binary state. 
* For my work/research in assembly industries, I frequently encounter programming in Python and working with REST and MQTT. I thought it would be nice to learn more about this, the pains of long-term-support and making packages in a private project.
* I started this project in 2022, where I decided to work with Raspberry Pi for Python, long-term support, and a western product (I think ESPHome is far better at what I do and need, though I have minor personal difficulty with the ESP chip and the consideration above is still dominant).
* To my best programming knowledge and searching skills, I found that the built-in or official remote GPIO option was not able to recover after a reboot ([see e.g. this issue](https://github.com/home-assistant/core/issues/116007)). further I did not found any other viable remote GPIO package for Home Assistant (except for HACS, which I prefere not to use for support issues).

## Contributing
For the time being, I highly appreciate feedback and suggestions to update or improve the code. Later, I may decide to allow contributors.

<!-- ## Authors and acknowledgment
Show your appreciation to those who have contributed to the project. -->

## License
For the time being, I use  the MIT license.

## Project Status
This is the third, and the first public, iteration of my privately developed code with the intention to make it generically suitable and provide (myself) long-term support and future compatibility. As a private project, don't expect a high pace of development and support as I am the only contributor.

## Known Issues/Bugs

* Count type pin device is not fully working.
* When providing a none existing Home Assistant ip-adres, the startup proces pauses to keep reaching for Home Assistant. This should be send to a background proces or even made optional in order to facilitate working without Home Assistant. 
* Needs testing to see what happens when Home Assistant is offline during a webhook update.