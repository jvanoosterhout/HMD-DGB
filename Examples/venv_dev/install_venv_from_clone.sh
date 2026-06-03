#!/bin/bash
sudo apt -y install python3-venv
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
# pre-commit install
# pre-commit run --all-files
# python -m build -v
