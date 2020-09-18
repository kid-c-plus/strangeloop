import time
import rpi

print("initializing...")

a = rpi.SPI()
push1 = rpi.GPIO(14, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
push2 = rpi.GPIO(20, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
toggleswitch = rpi.GPIO(12, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
footswitch = rpi.GPIO(15, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
led = rpi.GPIO(16, rpi.GPIO.FSEL.OUTPUT)

try:
    while True:
        print("pushbutton one: %d\npushbutton two: %d\ntoggle switch: %d\nfootswitch: %d" % (push1.read(), push2.read(), toggleswitch.read(), footswitch.read()))
        print(a.read_frame())
        led.toggle()
        time.sleep(1)
except KeyboardInterrupt:
    print("closing...")
    led.turn_off()
    a.__del__()
