# --------------------------------------------------------------
#   Class handling all low-level Pedal-Pi board communications
# --------------------------------------------------------------

import libbcm2835._bcm2835 as soc
from enum import Enum
import ctypes

soc_init = False
soc_spi_begin = False

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
        global soc_spi_begin
        if not soc_spi_begin:
            self.__spi_bus_init__()
            soc_spi_begin = True

    def __del__(self):
        global soc_spi_begin
        if soc_spi_begin:
            soc.bcm2835_spi_end()
            soc_spi_begin = False
        super().__del__()

    def __spi_bus_init__(self):
        # assert soc.bcm2835_spi_begin(), "BCM2835 SPI initialization failed. Are you root?"

        soc.bcm2835_spi_begin() 
        
        # SPI bus initialization values taken from ElectroSmash Pedal-Pi Looper C Code: https://www.electrosmash.com/forum/pedal-pi/235-looper-guitar-effect-pedal
        soc.bcm2835_spi_setBitOrder(soc.BCM2835_SPI_BIT_ORDER_MSBFIRST)
        soc.bcm2835_spi_setDataMode(soc.BCM2835_SPI_MODE0)
        soc.bcm2835_spi_setClockDivider(soc.BCM2835_SPI_CLOCK_DIVIDER_64)
        soc.bcm2835_spi_chipSelect(soc.BCM2835_SPI_CS0)
        soc.bcm2835_spi_setChipSelectPolarity(soc.BCM2835_SPI_CS0, soc.LOW)

    def read_frame(self):
        send_buf = ctypes.create_string_buffer(b"\x01\x00\x00")
        recv_buf = ctypes.create_string_buffer(b"\x00\x00\x00")
        soc.bcm2835_spi_transfernb(send_buf, recv_buf, 3)
        return int.from_bytes(recv_buf[2], "big") + ((int.from_bytes(recv_buf[1], "big") & 0x0F) << 8); 
        
