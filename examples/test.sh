#!/bin/bash

pip uninstall requests-ip-rotator -y
pip install ../.
python ../examples/sample.py