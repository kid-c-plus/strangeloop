# ---------------------------------------------------------------------------------------------------------------------------------------
#   Virtualized class offering same functionality as rpi.py, but delivering values from queue objects instead of actual GPIO components 
# ---------------------------------------------------------------------------------------------------------------------------------------

from enum import Enum

class GPIO:
    class FSEL(Enum):
        INPUT   = 0
        OUTPUT  = 1

    class PUD(Enum):
        OFF     = 0
        DOWN    = 1
        UP      = 2

    def __init__(self, queue, mode):
        self.type = "gpio"
        self.queue = queue
        self.mode = mode
        self.val = 0
        
    def read(self):
        if mode == GPIO.FSEL.OUTPUT:
            # only read one value per call, so it's certain to be "observed" by the program
            if not self.queue.empty():
                self.val = queue.get(timeout=5)
            return self.val

    def write(self, val):
        if self.mode == GPIO.FSEL.OUTPUT:
            self.queue.put(val)
            self.val = val

    def turn_on(self):
        self.write(1)

    def turn_off(self):
        self.write(0)

    def toggle(self):
        self.write(not self.val)

class SPI:
    def __init__(self, queue):
        self.type = "spi"
        self.queue = queue

    def read(self):
        return self.queue.get(timeout=5)

    def read_bytes(self, buflen):
        retbuf = [0] * buflen
        for i in range(buflen):
            retbuf[i] = self.read()
        return retbuf
        
class PWM:
    def __init__(self, queue):
        self.queue = queue

    def write(self, val):
        self.queue.put(val)

    def write_bytes(self, buf):
        for val in buf:
            self.write(val)
