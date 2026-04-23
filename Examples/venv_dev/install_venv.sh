#!/bin/bash
mkdir hmd-dgb-project && cd hmd-dgb-project
git clone https://github.com/jvanoosterhout/HMD-DGB.git
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
pip install -e HMD-DGB[dev]
pre-commit install
pre-commit run --all-files
python -m build -v
