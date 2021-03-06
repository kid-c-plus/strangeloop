#!/usr/bin/python3

import pedal
import time
import logging
import sys
sys.path.append("../../common")

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

a = pedal.Pedal(debug=True)
a.run()
try:
    input("Running pedal...")
except KeyboardInterrupt:
    pass
a.end()
