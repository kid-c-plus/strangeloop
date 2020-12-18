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

from pedal import pedal

# unit tests specifically related to pedal operation - adding and removing loops, joining sessions, etc
# stored here so that the pedal constructor can be imported directly without triggering app/__init__.py

NICKNAME = "rick@%s" % platform.node()

ADDLOOPBUTTON = 'pushbutton2'
DELLOOPBUTTON = 'pushbutton1'

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

        self.pedal = pedal.Pedal(loggername="%s.pedal" % __name__, rpisleep=0, virtualize=True, vqueues=self.pedalvqueues, apargs={'virtualize' : True, 'vqueues' : self.apvqueues, 'itertimestamp' : True})

    def tearDown(self):
        logger.info("tearing down...")
    
        self.pedal.end()
    
    # helper methods
    def writeinputbits(self, inputbits):
        for ib in inputbits:
            self.apvqueues['audioin'].put(ib)

    def waitonaudioin(self):
        while not self.apvqueues['audioin'].empty():
            logger.info("waiting on audio in...")
            time.sleep(0.5)

    def readoutputbits(self, outputbits):
        for obi in range(outputbits.size):
            outputbits[obi] = self.apvqueues['audioout'].get()

    def pushbutton(self, button):
        if button in self.pedalvqueues:
            self.pedalvqueues[button].put(pedal.PUSHBUTTON_PRESS)
            self.pedalvqueues[button].put(pedal.PUSHBUTTON_RELEASE)

    # multithreaded queue behavior gets so odd that the best way to avoid headaches is to undertake each test one at a time, starting a new process each time
    def test(self):
        testManyLoops(self)

# preliminary test to ensure reading input from queue works as expected
def testQueueInput(self):
    inputbits   = np.random.randint(low=1, high=500, size=100)
    outputbits  = np.zeros_like(inputbits)
    
    self.pedal.run()

    self.writeinputbits(inputbits)

    self.readoutputbits(outputbits)
    
    assert np.array_equal(outputbits, inputbits)

def testSingleLoop(self):
    loop            = np.random.randint(low=1, high=200, size=200)
    postloopinput   = np.random.randint(low=1, high=200, size=200)
    norm            = np.mean(loop, dtype=int)
    overdub         = loop + postloopinput - norm 
    expectedoutput  = np.append(loop, overdub)

    # needs to be "pressed" before starting or else audio processor will hang on and read first input before registering to start loop
    self.pushbutton(ADDLOOPBUTTON)

    time.sleep(1)

    self.pedal.run()

    time.sleep(1)

    # write all but last bit, then press button, then add last bit
    # otherwise it will hang for post-loop audio input before registering addloopbutton
    self.writeinputbits(loop[:-1])

    time.sleep(1)

    self.pushbutton(ADDLOOPBUTTON)

    time.sleep(1)

    self.writeinputbits(loop[-1:])
    self.writeinputbits(postloopinput)

    outputbits = np.zeros_like(expectedoutput)
    self.readoutputbits(outputbits)

    # print("expected: %s" % str(expectedoutput))
    # print("recieved: %s" % str(outputbits))

    assert np.array_equal(outputbits, expectedoutput)

def testManyLoops(self):
    expectedoutput = np.empty(0, dtype=int)

    pedalrun = False

    for i in range(5):
        loop = np.random.randint(low=1, high=200, size=50)
        if len(expectedoutput) >= len(loop):
            composite = expectedoutput[-1 * loop.size:]
            norm = np.mean(composite, dtype=int)
            overdub = composite + loop - norm
            expectedoutput = np.append(expectedoutput, overdub)
        else:
            expectedoutput = np.append(expectedoutput, loop)

        if not pedalrun:
            self.pushbutton(ADDLOOPBUTTON)
            time.sleep(1)
            self.pedal.run()
            pedalrun = True

        self.writeinputbits(loop[:-1])

        time.sleep(1)

        self.pushbutton(ADDLOOPBUTTON)
        if i < 4:
            self.pushbutton(ADDLOOPBUTTON)

        time.sleep(2)

        self.writeinputbits(loop[-1:])

    outputbits = np.zeros_like(expectedoutput)
    self.readoutputbits(outputbits)

    assert np.array_equal(outputbits, expectedoutput)

if __name__ == "__main__":
    unittest.main()
