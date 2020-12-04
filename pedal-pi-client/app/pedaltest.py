#!/usr/bin/python3

import pedal
import time
import logging

logging.basicConfig(filename='/var/log/strangeloop/pedal.log', level=logging.DEBUG)

a = pedal.Pedal(debug=True)
try:
    input("Running pedal...")
except KeyboardInterrupt:
    pass
a.end()
