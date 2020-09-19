import rpi
import datetime as dt

print("initializing...")

a = rpi.SPI()
o = rpi.PWM((18, 13))
push1 = rpi.GPIO(14, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
push2 = rpi.GPIO(20, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
toggleswitch = rpi.GPIO(12, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
footswitch = rpi.GPIO(15, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
led = rpi.GPIO(16, rpi.GPIO.FSEL.OUTPUT)

lastupdate = None
updatedelta = dt.timedelta(seconds=1)

try:
    while True:
        spi_input = a.read()
        o.write(spi_input)

        now = dt.datetime.now()
        if not lastupdate or (now - lastupdate) > updatedelta:
            print("pushbutton one: %d\npushbutton two: %d\ntoggle switch: %d\nfootswitch: %d" % (push1.read(), push2.read(), toggleswitch.read(), footswitch.read()))
            led.toggle()
            lastupdate = now

except KeyboardInterrupt:
    print("closing...")
    led.turn_off()
    a.__del__()
