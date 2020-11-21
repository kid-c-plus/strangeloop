# --------------------------------------------------------------
#   Class handling all low-level Pedal-Pi board communications
# --------------------------------------------------------------

import libbcm2835._bcm2835 as soc
from enum import Enum
import ctypes

soc_init = False
spi_init = False
pwm_init = False

# duration, in ms, to wait after consequential GPIO value read to account for debouncing
RPI_DEBOUNCE_DELAY = 1000

# duration, in ms, to wait after initialization to read/write from components
RPI_INIT_DELAY = 250

# delay to account for button debouncing, though I'm not sure it's a HUGE deal with a footswitch specifically
def debounce_delay(delay=RPI_DEBOUNCE_DELAY):
    soc.bcm2835_delay(delay)

class Component:
    def __init__(self):
        self.type = "basic"
        global soc_init
        if not soc_init:
            assert soc.bcm2835_init(), "BCM2835 initialization failed. Are you root?"
            soc_init = True

    def __del__(self):
        global soc_init
        if soc_init:
            assert soc.bcm2835_close(), "BCM2835 close failed."
            soc_init = False

class GPIO(Component):
    class FSEL(Enum):
        INPUT   = soc.BCM2835_GPIO_FSEL_INPT
        OUTPUT  = soc.BCM2835_GPIO_FSEL_OUTP

    class PUD(Enum):
        OFF     = soc.BCM2835_GPIO_PUD_OFF
        DOWN    = soc.BCM2835_GPIO_PUD_DOWN
        UP      = soc.BCM2835_GPIO_PUD_UP

    def __init__(self, pin, mode, pud=None):
        super().__init__()
        self.type = "gpio"
        self.pin = pin
        self.mode = mode
        soc.bcm2835_gpio_fsel(pin, mode.value)
        if mode == GPIO.FSEL.OUTPUT:
            self.val = 0
        if pud:
            soc.bcm2835_gpio_set_pud(pin, pud.value)
        soc.bcm2835_delay(RPI_INIT_DELAY)
        
    def read(self):
        return soc.bcm2835_gpio_lev(self.pin) if self.mode == GPIO.FSEL.INPUT else 0

    def write(self, val):
        if self.mode == GPIO.FSEL.OUTPUT:
            soc.bcm2835_gpio_write(self.pin, val)
            self.val = val

    def turn_on(self):
        self.write(1)

    def turn_off(self):
        self.write(0)

    def toggle(self):
        self.write(not self.val)

class SPI(Component):
    def __init__(self):
        super().__init__()
        self.type = "spi"
        global spi_init
        if not spi_init:
            self.__spi_bus_init__()
            spi_init = True
        soc.bcm2835_delay(RPI_INIT_DELAY)

    def __del__(self):
        global spi_init, soc_init
        if spi_init and soc_init:
            soc.bcm2835_spi_end()
            spi_init = False
        super().__del__()

    def __spi_bus_init__(self):
        soc.bcm2835_spi_begin() 
        
        # SPI bus initialization values taken from ElectroSmash Pedal-Pi Looper C Code: https://www.electrosmash.com/forum/pedal-pi/235-looper-guitar-effect-pedal
        soc.bcm2835_spi_setBitOrder(soc.BCM2835_SPI_BIT_ORDER_MSBFIRST)
        soc.bcm2835_spi_setDataMode(soc.BCM2835_SPI_MODE0)
        soc.bcm2835_spi_setClockDivider(soc.BCM2835_SPI_CLOCK_DIVIDER_64)
        soc.bcm2835_spi_chipSelect(soc.BCM2835_SPI_CS0)
        soc.bcm2835_spi_setChipSelectPolarity(soc.BCM2835_SPI_CS0, soc.LOW)

    def read(self):
        send_buf = ctypes.create_string_buffer(b"\x01\x00\x00")
        recv_buf = ctypes.create_string_buffer(b"\x00\x00\x00")
        soc.bcm2835_spi_transfernb(send_buf, recv_buf, 3)
        return int.from_bytes(recv_buf[2], "big") + ((int.from_bytes(recv_buf[1], "big") & 0x0F) << 8); 

    def read_bytes(self, buflen):
        retbuf = [0] * buflen
        for i in range(buflen):
            retbuf[i] = self.read()
        return retbuf
        
class PWM(Component):
    def __init__(self, pins):
        super().__init__()
        self.pins = pins
        global pwm_init
        if not pwm_init:
            self.__pwm_init__()
            pwm_init = True
        soc.bcm2835_delay(RPI_INIT_DELAY)

    def __del__(self):
        super().__del__()

    def __pwm_init__(self):
        # PWM initialization values also taken from ElectroSmash Looper C Code
        soc.bcm2835_gpio_fsel(self.pins[0],soc.BCM2835_GPIO_FSEL_ALT5)
        soc.bcm2835_gpio_fsel(self.pins[1],soc.BCM2835_GPIO_FSEL_ALT0)
        soc.bcm2835_pwm_set_clock(2)
        soc.bcm2835_pwm_set_mode(0, 1, 1)
        soc.bcm2835_pwm_set_range(0, 64)
        soc.bcm2835_pwm_set_mode(1, 1, 1)
        soc.bcm2835_pwm_set_range(1, 64)

    def write(self, val):
        soc.bcm2835_pwm_set_data(1, val & 0x3F)
        soc.bcm2835_pwm_set_data(0, val >> 6)

    def write_bytes(self, buf):
        for val in buf:
            self.write(val)
