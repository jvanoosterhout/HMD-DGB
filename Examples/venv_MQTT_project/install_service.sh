script_name=API_example.py
service_name=API_example
service_doel="GPIOpinAPI"

# get curent path and set the system path
global_path=`pwd`

cd /lib/systemd/system/

# write the service file to the service file
echo "[Unit]
Description=Python service om de $service_doel
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=$global_path
ExecStart=$global_path/venv/bin/python3 $global_path/$script_name
Restart=on-abort

[Install]
WantedBy=multi-user.target" | sudo tee $service_name.service

# give python script and service execution right
chmod +x $global_path/$script_name
sudo chmod 644 /lib/systemd/system/$service_name.service

# reload the deamon and enable the service
sudo systemctl daemon-reload
sudo systemctl enable $service_name.service

# start the service and show its first logs (allow you to verify that it is working)
cd global_path
sudo systemctl start $service_name.service
echo "service started, showing output. You can safely press ctrl+c or close the terminal."
journalctl -f -u $service_name.service
