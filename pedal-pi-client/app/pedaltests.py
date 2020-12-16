#!/usr/bin/python3
import unittest
import numpy as np
import time
import os
import sys
import queue
import multiprocessing
import signal
import platform
import logging

from pedal import Pedal

# unit tests specifically related to pedal operation - adding and removing loops, joining sessions, etc
# stored here so that the pedal constructor can be imported directly without triggering app/__init__.py

NICKNAME = "rick@%s" % platform.node()

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
    
        self.pedalvqueues = {
            'pushbutton1'   : queue.Queue(),
            'pushbutton2'   : queue.Queue(),
            'toggleswitch'  : queue.Queue(),
            'footswitch'    : queue.Queue(),
            'led'           : queue.Queue()
        }

        self.apvqueues = {
            'audioin'   : multiprocessing.Queue(),
            'audioout'  : multiprocessing.Queue()
        }


        self.pedal = Pedal(loggername="%s.pedal" % __name__, virtualize=True, vqueues=self.pedalvqueues, apargs={'virtualize' : True, 'vqueues' : self.apvqueues, 'itertimestamp' : True})

    def tearDown(self):
        logger.info("tearing down...")
    
        self.pedal.end()

    # preliminary test to ensure reading input from file works as expected
    def testFileInput(self):
        inputbits   = np.random.randint(low=1, high=500, size=100)
        outputbits  = np.zeros_like(inputbits)
        
        self.pedal.run()

        for ib in inputbits:
            self.apvqueues['audioin'].put(ib)

        for obi in range(outputbits.size):
            outputbits[obi] = self.apvqueues['audioout'].get()

        assert np.array_equal(outputbits, inputbits)

'''
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
'''
        
if __name__ == "__main__":
    unittest.main()
