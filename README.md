# GPIOpinAPI

## Overview
GPIOpinAPI is a Python package designed to simplify the interaction with GPIO pins on a raspberry pi from another system via REST calls. 
It provides an easy-to-use API for configuring, reading, and writing to GPIO pins, making it ideal for domotica and IoT projects. A special feature is to provide a Home Assistant webhook in the configuration of input type pins.

## Features
* Easy Configuration: Quickly set up GPIO pins with simple REST commands.
* Read/Write Operations: Perform read and write operations on GPIO pins.
* Local push updates: send and webhook update to Home Assistant when an input device type pin is (de)activated.
* Swagger UI docs: check and test the API capabilities. 

## Installation 

Tested on Raspberry pi 4 and zero with bookworm (64-bit). 

### run it yourself

* create and activate a venv 
* install the package via ```pip install git+https://gitlab.com/jotd/gpiopinapi.git@0.0.1#egg=PinAPI```
* run the /gpiopinapi/Examples/API_example.py 
* check http://{[the-pi-ip-adress]}:11411/docs

### use the venv example 

* clone the project (or just the /gpiopinapi/Examples/venv_project folder)
* run the install_venv.sh
* run the install_service.sh
* check http://{[the-pi-ip-adress]}:11411/docs

### use docker 

* todo

## Support
Please feel free to post issues or questions on https://gitlab.com/jotd/gpiopinapi/-/issues. Though, know this is an spare time project. 

## Roadmap

* Finalyse count type pin. Use-case is a water flow meter which generates pulles based on the flowrate, alike this one https://www.otronic.nl/nl/water-flow-sensor.html
* Add a time-series-out type pin. Use-case is to feed an RF transmitter alike this one https://www.otronic.nl/nl/433mhz-rf-zender-en-ontvanger-140567829.html to send signals to an RF IR pannel (in my case the non-wifi version of this one: https://www.gaslooswonen.nl/qh-hl-serie-wifi-infraroodpaneel-met-led-145578285.html#gerelateerde-producten). A non-public version of gpiopinapi is already able to send hardcodes signals. 
* Add a time-series-in type pin. Use-case is to read RF signals. Processing and cutting out the functional part of a time series RF signal may not be posible within the API. 
* Add docker setup. Use-case is to Making this package more robust to the ever changing versions of systems and software. 
* Extend pin capablilities. Add e.g. support for input pin devices to trigger only on when_activated or when_deactivated.  
* Improve the Swagger UI docs. The docs currenly provide a basic, though confusing overview. For example, the example payload of a POST does not change when the pin_type is changed. Also all query parameters are shown for all pin types. 


## Usage

You can test the API most easyly via http://{[the-pi-ip-adress]}:11411/docs. The documentation and examples may seem somewhat confusing for the post and get pin endpoint. Though schemas are shown at the bottem of the page. 

When intergating with Home Assistant, you may like the two samples below. thes samples can be placed in /homeassistant/configuration.yaml. Or in a separate .yaml file in "packages" directory which you include in the configuration.yaml via e.g.:
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
    state_resource: http://192.168.70.20:11411/api/v1/pin/out?pin=21&initial=0&active_state=0&value=0
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

The second sample is gate of garage door. Having your door activate with a slight tough while your are not near the gate/door, or while your chiled plays with your phone seems trick, therefore the "password" comes in handy. It is just a simple double check you want to open the gate/door. Further in this specific example, my garage door is puls triggered the same puls is used to open, close or stop the door. Meaning you can have such senaris: 
* click --> opening --> wait --> fully opend --> click --> closing wait --> fully opeclose
* click --> opening --> click --> stop (somewhere while opening)--> click --> closing
For your own gate you may be able to set different pins fr the open, close and/or stop action. 

Note that the below example and a pi does not suffiece, you may need a relay board to isolate the  electric circuits of the pi and gate/door. 


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

## Contributing
For the time being I would apreciate feedback and suggestions to update and improve the code. Later I may decide to allow contributors. 

<!-- ## Authors and acknowledgment
Show your appreciation to those who have contributed to the project. -->

## License
For the time being I commit tho the MIT licence. 

## Project status
This is the third itteration of my privatly developed code with the intention to make it generically suitable and provide (myself) long term support and future compatibility. As a private project, don't expect a too high pace of development and support as long as I am the only contributor. 

## Known issus/bugs

* count type pin device is not fully working. 
* not sure what happens when providing no or an incorrect Home Assistant IP adress. 
