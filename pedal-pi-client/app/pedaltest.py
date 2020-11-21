#!/usr/bin/python3

# import faulthandler
# faulthandler.enable()
import pedal
import time

''' for _ in range(5):
    a = pedal.Pedal()
    time.sleep(10)
    print("deleting pedal")
    a.end()
    time.sleep(2) '''

a = pedal.Pedal(debug=True)
input("Running pedal...")
a.end()
