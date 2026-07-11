#!/bin/bash

## user parameters
# systemd service parameters
service_name=42_controller
service_description="controller van de meterkast"

# DGB service parameters
name="42-controller"
broker="192.168.1.42"
port="1883"
username="mqtt_broker"
password="mqtt_broker"
location="area-42"
rate=300

# desired install directory
cd ~/Myservices/Service42

## script
sudo apt install -y gcc python3-dev build-essential
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
pip install git+https://github.com/jvanoosterhout/HMD-DGB.git

# get curent path and set the system path
global_path=`pwd`

cd /lib/systemd/system/

# write the service file to the service file
echo "[Unit]
Description=Python service voor de $service_description
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=$global_path
ExecStart=$global_path/venv/bin/python3 -m DGB.DGBservice --name $name --broker $broker --port $port --username $username --password $password --location $location --rate $rate

Restart=always
RestartSec=15s

[Install]
WantedBy=multi-user.target" | sudo tee $service_name.service

# give python script and service execution right
# chmod +x $global_path/$sub_folder/$script_name
sudo chmod 644 /lib/systemd/system/$service_name.service

sudo systemctl daemon-reload
sudo systemctl enable $service_name.service

sudo systemctl start $service_name.service
echo "service started, showing output. You can safely press ctrl+c or close the terminal."
journalctl -f -u $service_name.service
