#!/usr/bin/python3
import unittest
import numpy as np
import time
import os
import sys
import signal
import platform
import logging

from pedal import Pedal

# unit tests specifically related to pedal operation - adding and removing loops, joining sessions, etc
# stored here so that the pedal constructor can be imported directly without triggering app/__init__.py

NICKNAME = "rick@%s" % platform.node()

# sleep for ten seconds while pedal runs through test file
PEDAL_OP_SLEEP = 5

INPUT_FILE = "test.in"
OUTPUT_FILE = "test.out"

# log to stdout
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s():%(lineno)d - %(message)s'))
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# suppress informational logs from pedal
sublogger = logging.getLogger("%s.pedal" % __name__)
sublogger.setLevel(logging.WARNING)

class OfflineTestCase(unittest.TestCase):

    def setUp(self):
        logger.info("setting up...")

        def handler(signal, frame):
            logger.error('CTRL-C pressed!')
            self.pedal.end()
            sys.exit(0)

        signal.signal(signal.SIGINT, handler)
        self.pedal = Pedal(audioloadinput=True, audioinfile=INPUT_FILE, audiosaveoutput=True, audiooutfile=OUTPUT_FILE, audioplayoutput=False, loggername="%s.pedal" % __name__)

    def tearDown(self):
        logger.info("tearing down...")
    
        self.pedal.end()
        if os.path.exists(INPUT_FILE):
            os.remove(INPUT_FILE)
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)

    def writeInput(self, inputstr):
        with open(INPUT_FILE, mode="w") as infile:
            infile.write(inputstr)

    def readOutput(self):
        with open(OUTPUT_FILE) as outfile:
            return outfile.read().strip()

    def strRep(self, nparr):
        return " ".join([str(b) for b in nparr])

    # preliminary test to ensure reading input from file works as expected
    def testFileInput(self):
        inputbits = np.random.randint(low=1, high=500, size=100)
        inputstr = self.strRep(inputbits)
        
        self.writeInput(inputstr)
        self.pedal.run()
        time.sleep(PEDAL_OP_SLEEP)
        outputstr = self.readOutput()
        expectedoutput = inputstr

        assert outputstr == expectedoutput

    def testSingleLoop(self):
        loop = np.random.randint(low=1, high=500, size=100)
        postloopinput = np.random.randint(low=1, high=500, size=100)
        norm = np.mean(loop, dtype=int)
        overdub = loop + postloopinput - norm 
        inputstr = "recording %s recording %s" % (self.strRep(loop), self.strRep(postloopinput))
       
        self.writeInput(inputstr) 
        self.pedal.run()
        time.sleep(PEDAL_OP_SLEEP)
        outputstr = self.readOutput()

        expectedoutput = "%s %s" % (self.strRep(loop), self.strRep(overdub))

        assert outputstr == expectedoutput
        

if __name__ == "__main__":
    unittest.main()
