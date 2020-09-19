import uuid
import requests
import time
import atexit
from threading import Thread, Event, main_thread
from datetime import datetime
from io import BytesIO
from . import rpi

# -------------
#   Constants
# -------------

SERVER_URL = "http://192.168.1.72:5000/"

SUCCESS_RETURN = "True"
FAILURE_RETURN = "False"
FULL_RETURN = "Full"
NONE_RETURN = "None"

END_LOOP_SLEEP = 0.1
COMPOSITE_POLL_INTERVAL = 2

PUSHBUTTON1     = 14
PUSHBUTTON2     = 20
TOGGLESWITCH    = 12
FOOTSWITCH      = 15
LED             = 16
AUDIO_OUT       = {
    'PWM0'  : 18,
    'PWM1'  : 13
}

# pushbutton GPIO values
PUSHBUTTON_PRESS    = 0
PUSHBUTTON_RELEASE  = 1

# toggle switch GPIO values
TOGGLESWITCH_OFF    = 0
TOGGLESWITCH_ON     = 1

# footswitch GPIO values
FOOTSWITCH_MON      = 0
FOOTSWITCH_BYPASS   = 1

# class handling all the basic functionality of a looper pedal. the Flask UI receives and interacts with an instance of this class
class Pedal():

    # Thread superclass that periodically polls server for new additions to the composite
    class CompositePollingThread(Thread):
        def __init__(self, pedal):
            Thread.__init__(self)
            self.stop = Event()
            self.pedal = pedal
            self.timestamp = datetime.now().timestamp()

        def run(self):
            while not self.stop.wait(COMPOSITE_POLL_INTERVAL):
                if self.pedal.getcomposite(timestamp=self.timestamp):
                    self.timestamp = datetime.now().timestamp()


    # Thread superclass that reads audio from AUDIO_IN and sends it to AUDIO_OUT along with composite data, if it is present
    # Does not monitor Raspberry Pi buttons for user input
    class AudioProcessingThread(Thread):
        def __init__(self, pedal, daemon=True):
            Thread.__init__(self, daemon=daemon)
            self.pedal = pedal
            
        def run(self):
            compositeindex = 0
            while self.pedal.running:
                if self.pedal.monitoring:
                    inputbits = self.pedal.audioin.read()
                    outputbits = inputbits
                    if self.pedal.compositedata:
                        compositebits = self.pedal.compositedata[compositeindex]
                        outputbits = (inputbits + compositebits) >> 1
                        compositeindex = (compositeindex + 1) % len(self.pedal.compositedata)
                    else:
                        compositeindex = 0

                    if self.pedal.recording:
                        # (outputbits + inputbits) >> 1: add the two signals together and divide them by two, providing the mean
                        # either there is no composite yet, or we haven't yet exceeded the length of the composite
                        # some loop pedals act differently, but we're just gonna truncate everything after the first take
                        if not self.pedal.compositedata or len(self.pedal.loopdata) < len(self.pedal.compositedata):
                            if not self.pedal.compositedata or len(self.pedal.loopdata) < len(self.pedal.compositedata):
                                self.pedal.loopdata.append(inputbits)
                            if self.pedal.firstrecpass:
                                # we need to keep track of where we started recording relative to the composite
                                self.pedal.loopoffset = compositeindex
                                self.pedal.firstrecpass = False
                    self.pedal.audioout.write(outputbits)

    # Thread superclass to monitor RPi components and change pedal state accordingly
    class RPiMonitoringThread(Thread):
        def __init__(self, pedal):
            Thread.__init__(self)
            self.pedal = pedal

        def run(self):
            while self.pedal.running:
                debounce_delay = False

                footswitch_val  = self.pedal.footswitch.read()
                pushbutton1_val = self.pedal.pushbutton1.read()
                pushbutton2_val = self.pedal.pushbutton2.read()

                if footswitch_val == FOOTSWITCH_MON and not self.pedal.monitoring:
                    self.pedal.monitoring = True
                    debounce_delay = True
                elif footswitch_val == FOOTSWITCH_BYPASS and self.pedal.monitoring:
                    self.pedal.monitoring = False
                    if self.pedal.recording:
                        self.pedal.endloop()
                    debounce_delay = True

                if pushbutton1_val == PUSHBUTTON_PRESS:
                    self.pedal.removeloop()
                    debounce_delay = True

                if pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and not self.pedal.recording:
                    self.pedal.startloop()
                    debounce_delay = True
                elif pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and self.pedal.recording:
                    self.pedal.endloop()
                    debounce_delay = True

                if debounce_delay:
                    # delay to account for button debouncing, though I'm not sure it's a HUGE deal with a footswitch specifically
                    rpi.debounce_delay()


    def __init__(self, debug=False):
        self.pushbutton1    = rpi.GPIO(PUSHBUTTON1, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.pushbutton2    = rpi.GPIO(PUSHBUTTON2, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.toggleswitch   = rpi.GPIO(TOGGLESWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.footswitch     = rpi.GPIO(FOOTSWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.led            = rpi.GPIO(LED, rpi.GPIO.FSEL.OUTPUT)
        self.audioin        = rpi.SPI()
        self.audioout       = rpi.PWM((AUDIO_OUT['PWM0'], AUDIO_OUT['PWM1']))

        self.led.turn_on()

        uuidnode = uuid.getnode()
        self.mac = ':'.join(("%012X" % uuidnode)[i:i+2] for i in range(0, 12, 2))
        self.sessionid = None
        self.owner = False
        self.sessionmembers = None

        # check initial session membership
        try:
            self.getsession(timeout=1)
            if self.sessionid:
                self.getmembers()
            self.online = True
        except requests.exceptions.ConnectionError:
            self.online = False

        self.compositedata = None
        self.lastcomposite = None
        self.compositepollthread    = Pedal.CompositePollingThread(pedal=self)
        self.processaudiothread     = Pedal.AudioProcessingThread(pedal=self, daemon=True)
        self.monitorrpithread       = Pedal.RPiMonitoringThread(pedal=self)

        self.loopdata = []
        self.loopoffset = 0
        self.running = True
        self.monitoring = False
        self.recording = False

        self.loops = []
        self.loopindex = 1

        self.processaudiothread.start()
        self.monitorrpithread.start()

        self.debug = debug
        if debug:
            print(self.newsession("rick"))

        self.led.turn_off()

    def __del__(self):
        if self.compositepollthread:
            self.compositepollthread.stop.set()
        if self.monitorrpithread:
            self.monitorrpithread.stop.set()

        self.running = False

        self.led.turn_off()

    def newsession(self, nickname):
        serverresponse = requests.post(SERVER_URL + "newsession", data={'mac' : self.mac, 'nickname' : nickname}).text
        if serverresponse == FAILURE_RETURN:
            self.getsession()
        elif serverresponse != NONE_RETURN and serverresponse != FULL_RETURN:
            self.sessionid = serverresponse 
            self.owner = True
            self.compositepollthread.start()
            return SUCCESS_RETURN
        return serverresponse

    def endsession(self):
        serverresponse = requests.post(SERVER_URL + "endsession", data={'mac' : self.mac}).text
        if serverresponse == SUCCESS_RETURN:
            self.sessionid = None
            self.owner = False
            self.compositepollthread.stop.set()
        else:
            self.getsession()
        return serverresponse

    def joinsession(self, nickname, sessionid):
        serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text
        if serverresponse == FAILURE_RETURN:
            self.getsession()
        elif serverresponse == SUCCESS_RETURN:
            self.sessionid = sessionid
            self.owner = False
            self.compositepollthread.start()
        return serverresponse

    def leavesession(self):
        serverresponse = requests.post(SERVER_URL + "leavesession", data={'mac' : self.mac}).text
        if serverresponse == SUCCESS_RETURN:
            self.sessionid = None
            self.owner = False
            self.compositepollthread.stop.set()
        return serverresponse

    def getsession(self, **kwargs):
        serverresponse = requests.post(SERVER_URL + "getsession", data={'mac' : self.mac}, **kwargs).text
        if serverresponse != FAILURE_RETURN:
            if serverresponse == NONE_RETURN:
                self.sessionid = None
                self.owner = False
            else:
                self.sessionid, self.owner = serverresponse.split(":")
                self.owner = (self.owner == "owner")
                return SUCCESS_RETURN
        return serverresponse 

    def getmembers(self):
        serverresponse = requests.post(SERVER_URL + "getmembers", data={'mac' : self.mac}).text
        if serverresponse == FAILURE_RETURN:
            self.sessionmembers = []
        else:
            self.sessionmembers = serverresponse.split(",")
            return SUCCESS_RETURN
        return serverresponse

    # requests current composite from server
    # args:     timestamp: timestamp of last update
    # returns:  true if updated, false otherwise
    def getcomposite(self, timestamp=None):
        compositeresp = requests.post(SERVER_URL + "getcomposite", data={'mac' : self.mac, 'timestamp' : timestamp})
        if compositeresp.text != NONE_RETURN:
            self.compositedata = compositeresp.content
            return SUCCESS_RETURN
        return FAILURE_RETURN

    def startloop(self):
        self.recording = True
        self.firstrecpass = True
        self.led.turn_on()

    def endloop(self):
        self.recording = False
        self.led.turn_off()
        time.sleep(END_LOOP_SLEEP)
        # synchronize loop to existing composite
        if self.compositedata:
            if len(self.loopdata) < len(self.compositedata):
                self.loopdata += [0x00] * (len(self.compositedata) - len(self.loopdata))
            self.loopdata = self.loopdata[self.loopoffset:] + self.loopdata[:self.loopoffset]
            self.lastcomposite = self.compositedata
            print(self.loopdata[:min(len(self.loopdata), 100)])
            print(self.compositedata[:min(len(self.compositedata), 100)])
            print(self.loopdata == self.compositedata)
            self.compositedata = [(self.loopdata[i] + self.compositedata[i]) >> 1 for i in range(len(self.compositedata))]
            print(self.compositedata[:min(len(self.compositedata), 100)])
        else:
            self.compositedata = self.loopdata

        if self.sessionid:
            loopindex = self.loopindex
            self.loops.append(loopindex)
            self.loopindex += 1
            serverresponse = requests.post(SERVER_URL + "addtrack", data={'mac' : self.mac, 'index' : loopindex}, files={'wavdata' : BytesIO(self.loopdata)}).text
            self.loopdata = []
            self.getcomposite()
            return serverresponse

        self.loopdata = []
        return SUCCESS_RETURN

    def removeloop(self, index=None):
        if self.sessionid:
            if index:
                if index in self.loops:
                    self.loops.pop(self.loops.index(index))
                    return requests.post(SERVER_URL + "removetrack", data={'mac' : self.mac, 'index' : index}).text
                else:
                    return FAILURE_RETURN
            elif self.loopindex > 1:
                return requests.post(SERVER_URL + "removetrack", data={'mac' : self.mac, 'index' : self.loopindex - 1}).text
        else:
            # can only erase most recent loop if using without web session
            self.compositedata = self.lastcomposite
            return SUCCESS_RETURN            
