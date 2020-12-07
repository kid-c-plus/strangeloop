#!/usr/bin/python3
from app import flaskapp, pedal
import sys
import signal
# import logging

# logging.basicConfig(filename='/var/log/strangeloop/pedal.log', level=logging.DEBUG)
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

def handler(signal, frame):
    print('CTRL-C pressed!')
    pedal.end()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)
    flaskapp.run(host="0.0.0.0", port=80, debug=True, use_reloader=False)
    signal.pause()
