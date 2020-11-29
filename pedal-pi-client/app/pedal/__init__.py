import uuid
import json
import requests
import time
import atexit
from threading import Thread, Event, main_thread
from datetime import datetime
from io import StringIO
import numpy as np
from . import rpi

# -------------
#   Constants
# -------------

SERVER_URL = "http://192.168.1.72:5000/"

# string responses sent by server
SUCCESS_RETURN = "True"
FAILURE_RETURN = "False"
FULL_RETURN = "Full"
NONE_RETURN = "None"

# return value if unable to connect to server
OFFLINE_RETURN = "Offline"

END_LOOP_SLEEP = 0.0

# delays to pause between execution of Raspberry Pi and strangeloop server monitoring threads
# by far the most crucial thread is the AudioProcessing one
RPI_POLL_INTERVAL = 0.1
COMPOSITE_POLL_INTERVAL = 2

# numpy dtype to define loop & composite array entries
LOOP_ARRAY_DTYPE = [('value', int), ('timestamp', float)]

# add 10 seconds worth of loop time to the array each time its length is met
ARRAY_SIZE_SEC = 10

# how closely the composite playback needs to adhere to the actual time cycles elapsed
# that commment made no sense, sorry
# essentially the sample will play if it's within COMP_SAMPLE_WINDOW cycles of the original time it was played relative to the start of the loop
# otherwise it'll be dropped or held for the next cycle
COMP_SAMPLE_WINDOW = 5

# BCM pins for each device on the PCB
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

# -----------
#   Classes
# -----------

# ------------------------------------------------------------------------------
#   Pedal - class handling all the basic functionality of a looper pedal
#           the Flask UI receives and interacts with an instance of this class
# ------------------------------------------------------------------------------

class Pedal():

    # --------------------------------------------------------------------
    #   CompositePollingThread - Thread superclass that periodically 
    #   polls strangeloop server for new additions to the composite loop
    # --------------------------------------------------------------------

    class CompositePollingThread(Thread):

        # overloaded Thread constructor
        # args:     pedal: parent Pedal object that instantiated this thread

        def __init__(self, pedal):
            Thread.__init__(self)
            self.stop = Event()
            self.pedal = pedal
            self.timestamp = datetime.now().timestamp()

        # main thread execution loop

        def run(self):
            while self.pedal.running: 
                time.sleep(COMPOSITE_POLL_INTERVAL)

                # timestamp to determine whether any new data needs to be downloaded
                if self.pedal.getcomposite(timestamp=self.timestamp):
                    self.timestamp = datetime.now().timestamp()


    # --------------------------------------------------------------------
    #   AudioProcessingThread - Thread superclass that reads audio from 
    #                           AUDIO_IN and sends it to AUDIO_OUT along 
    #                           with composite data, if it is present
    #                           Does not monitor Raspberry Pi buttons
    #                           for user input, that's handled in the
    #                           RPiMonitoringThread. This is the most
    #                           important thread
    # --------------------------------------------------------------------

    class AudioProcessingThread(Thread):

        # overloaded Thread constructor
        # args:     pedal: parent Pedal object that instantiated this thread

        def __init__(self, pedal):
            Thread.__init__(self)
            self.pedal = pedal

            # used for calculating average sample period
            self.uptime = time.time()
            
            # used for diagnostics
            self.monitors = 0
            
            # debugging & diagnostic tools
            self.debug = True
            
            self.saveoutput = False
            if self.saveoutput:
                self.audiofile = open("/opt/strangeloop/pedal-pi-client/app/pedal/debug-%s.raw" % datetime.now().timestamp(), mode="w")
            
        # main thread execution loop

        def run(self):
            compositeindex = 0
            compositepassstart = 0
            looppassstart = 0
            while self.pedal.running:
                passtime = time.time()
                self.monitors += 1

                # update average cycle period every 100 cycles
                # this is a pedal property because the loop merging algorithm needs it
                if not self.monitors % 100:
                    self.pedal.avgsampleperiod = (passtime - self.uptime) / self.monitors

                debugpass = self.debug and not (self.monitors - 1) % 1000000

                if self.pedal.monitoring:

                    if self.pedal.recording:

                        if self.pedal.emptycomposite and self.pedal.firstrecpass:
                            # keep track of start time of first composite recording, so that timestamps can be normalized in relation to them
                            looppassstart = passtime
                            self.pedal.firstrecpass = False

                        # loop length is unbounded. add 10 seconds to loop np array
                        if self.pedal.loopiter >= len(self.pedal.loopdata):
                            self.pedal.loopdata = np.append(self.pedal.loopdata, np.zeros((int(ARRAY_SIZE_SEC / self.pedal.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE))

                    # read from AUX input
                    inputbits = self.pedal.audioin.read()
                    outputbits = inputbits

                    if not self.emptycomposite:

                        # playback timestamp relative to the start of the composite
                        compositetimestamp = passtime - compositepassstart

                        # find the proper place in the composite, where the current timestamp fits
                        while not (compositeindex == 0 or compositeindex == len(self.pedal.compositedata) - 1 or (self.pedal.compositedata[compositeindex] <= compositetimestamp and compositetimestamp <= self.pedal.compositedata[compositeindex + 1]))
                            compositeindex += 1 if compositetimestamp > self.pedal.compositedata[compositeindex + 1] else -1 

                        # play the closer of the two samples adjoining the current timestamp (or the index sample if the index is at the end of the array)
                        bestcompositeindex = compositeindex if (compositeindex == len(self.pedal.compositedata) - 1 or compositetimestamp - self.pedal.compositedata[compositeindex]['timestamp'] <= self.pedal.compositedata[compositeindex + 1] - compositetimestamp) else compositeindex + 1
                        compositebits = self.pedal.compositedata[bestcompositeindex]

                        # merge input and output bits
                        outputbits = inputbits + compositebits - (inputbits + compositebits) // 2

                        if self.pedal.recording:
                            # add merged input and composite, and average timestamps of composite recording and current input
                            self.pedal.compositedata[bestcompositeindex] = (out

                        # return to the start of the composite, and note the time that this playback began
                        if compositeindex >= len(self.pedal.compositedata) - 1:
                            compositeindex = 0
                            compositepassstart = passtime
                    else:
                        compositeindex = 0

                    if self.pedal.recording:
                        
                        if self.pedal.emptycomposite and self.pedal.firstrecpass:
                                # keep track of start time of first composite recording, so that timestamps can be normalized in relation to them
                                looppassstart = passtime
                                self.pedal.firstrecpass = False

                        # loop length is unbounded. add 10 seconds to loop np array
                        if self.pedal.loopiter >= len(self.pedal.loopdata):
                            self.pedal.loopdata = np.append(self.pedal.loopdata, np.zeros((int(ARRAY_SIZE_SEC / self.pedal.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE))

                        if self.pedal.emptycomposite:

                            # composite is also unbound on first loop
                            if self.pedal.loopiter >= len(self.pedal.compositedata):
                                self.pedal.compositedata = np.append(self.pedal.compositedata, np.zeros((int(ARRAY_SIZE_SEC / self.pedal.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE))

                            self.pedal.compositedata[self.pedal.loopiter] = (inputbits, passtime - looppassstart)

                        else:
                            # find the closest entry in the composite index to merge loop input signal with
                            inputsaveindex = max(0, compositeindex - 1)
                            while not (inputsaveindex == 0 or inputsaveindex == len(self.pedal.compositedata) - 1 or (self.pedal.compositedata[inputsaveindex - 1] <= compositetimestamp and 

                            

                        # write input data and timestamp relative to the start of the loop
                        self.pedal.loopdata[0][self.pedal.loopiter] = inputbits
                        self.pedal.loopdata[1][self.pedal.loopiter] = passtime - looprecstart
                        if debugpass:
                            print("recorded audio: %d" % inputbits)
                            print("timestamp: %f" % (passtime - looprecstart))
                        self.pedal.loopiter += 1

                    # write to AUX output
                    # cast to int
                    self.pedal.audioout.write(int(outputbits))

                    if self.saveoutput:
                        try:
                            self.audiofile.write("%d " % outputbits)
                        except:
                            pass

        # process end functions, mostly debugging

        def end(self):
            if self.debug:
                totaltime = time.time() - self.uptime
                print("monitoring frequency: %f Hz" % (self.monitors / totaltime))
            if self.saveoutput:
                self.audiofile.close()

    # -------------------------------------------------------------------
    # RPiMonitoringThread - Thread superclass to monitor RPi components 
    #                       and change pedal state accordingly
    # -------------------------------------------------------------------

    class RPiMonitoringThread(Thread):

        # overloaded Thread constructor
        # args:     pedal: parent Pedal object that instantiated this thread

        def __init__(self, pedal):
            Thread.__init__(self)
            self.pedal = pedal

        # main thread execution loop

        def run(self):
            while self.pedal.running:
                time.sleep(RPI_POLL_INTERVAL)

                # button reads are unreliable for a little while after a press
                debounce_delay = False

                footswitch_val  = self.pedal.footswitch.read()
                pushbutton1_val = self.pedal.pushbutton1.read()
                pushbutton2_val = self.pedal.pushbutton2.read()

                # pedal functions are only available when pedal is in monitor mode
                if footswitch_val == FOOTSWITCH_MON and not self.pedal.monitoring:
                    print("Footswitch set to monitor mode")
                    self.pedal.monitoring = True
                    debounce_delay = True

                # in bypass mode, the pedal can neither read from input nor write to output
                elif footswitch_val == FOOTSWITCH_BYPASS and self.pedal.monitoring:
                    print("Footswitch set to bypass mode")
                    self.pedal.monitoring = False
                    if self.pedal.recording:
                        self.pedal.endloop()
                    debounce_delay = True

                # you can only remove a loop if you aren't currently recording one
                if pushbutton1_val == PUSHBUTTON_PRESS and self.pedal.compositedata is not None and not self.pedal.recording:
                    print("Loop removed")
                    self.pedal.removeloop()
                    debounce_delay = True

                # start loop
                if pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and not self.pedal.recording:
                    print("Loop started")
                    self.pedal.startloop()
                    debounce_delay = True

                # end loop
                elif pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and self.pedal.recording:
                    print("Loop ended")
                    self.pedal.endloop()
                    debounce_delay = True

                if debounce_delay:
                    rpi.debounce_delay()


    # constructor class
    # args:     debug:  enable debugging log info

    def __init__(self, debug=False, webdebug=False):
        self.pushbutton1    = rpi.GPIO(PUSHBUTTON1, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.pushbutton2    = rpi.GPIO(PUSHBUTTON2, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.toggleswitch   = rpi.GPIO(TOGGLESWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.footswitch     = rpi.GPIO(FOOTSWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
        self.led            = rpi.GPIO(LED, rpi.GPIO.FSEL.OUTPUT)
        self.audioin        = rpi.SPI()
        self.audioout       = rpi.PWM((AUDIO_OUT['PWM0'], AUDIO_OUT['PWM1']))

        self.led.turn_on()

        # device MAC address is used as unique id in server interactions
        uuidnode = uuid.getnode()
        self.mac = ':'.join(("%012X" % uuidnode)[i:i+2] for i in range(0, 12, 2))
        self.sessionid = None
        self.owner = False
        self.sessionmembers = None

            # check initial session membership
        sessionresp = self.getsession(timeout=1)
        if self.sessionid:
            self.getmembers()

        # initialize with empty composite array
        self.compositedata = None
        self.lastcomposite = None

        # track whether composite has been recorded to before or not
        self.emptycomposite = True

        # initialize process threads
        self.compositepollthread    = Pedal.CompositePollingThread(pedal=self)
        self.processaudiothread     = Pedal.AudioProcessingThread(pedal=self)
        self.monitorrpithread       = Pedal.RPiMonitoringThread(pedal=self)

        # assume 4 kHz sampling interval, which is shitty, but what can you do
        self.avgsampleperiod = 1 / 4000

        # initialize empty loop data ~10 seconds long
        self.loopdata = np.zeros((2, int(ARRAY_SIZE_SEC / self.avgsampleperiod)), dtype=float)
        self.loopiter = 0
        self.loopoffset = 0

        # process thread flags
        self.running = True
        self.monitoring = False
        self.recording = False

        # when online, the user can delete loops by index
        # thus, it's not enough merely to track the number of loops
        # each one has a unique id on the server consisting of "MAC address:loop index"
        # the index iterates with each new loop and does not decrease on loop deletion
        self.loops = []
        self.loopindex = 1

        # start process threads
        self.processaudiothread.start()
        self.monitorrpithread.start()

        self.debug = debug
        self.webdebug = webdebug
        if webdebug:
            print(self.newsession("rick"))

        self.led.turn_off()

    # destructor method
    # set end flag so threads can exit gracefully

    def end(self):
        self.running = False

        # call process audio destructor
        if self.processaudiothread:
            self.processaudiothread.end()

        self.led.turn_off()

    # ------------------------------
    #   Server Interaction Methods
    # ------------------------------

    # create new session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   newly created session identifier on success, server response on failure, or OFFLINE_RETURN on failure to connect

    def newsession(self, nickname):
        try:
            serverresponse = requests.post(SERVER_URL + "newsession", data={'mac' : self.mac, 'nickname' : nickname}, **requestargs).text
            if serverresponse == FAILURE_RETURN:
                self.getsession()
            elif serverresponse != NONE_RETURN and serverresponse != FULL_RETURN:
                self.sessionid = serverresponse 
                self.owner = True
                self.compositepollthread.start()
                return SUCCESS_RETURN
            return serverresponse
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # end session
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect

    def endsession(self):
        try: 
            serverresponse = requests.post(SERVER_URL + "endsession", data={'mac' : self.mac}).text
            if serverresponse == SUCCESS_RETURN:
                self.sessionid = None
                self.owner = False
                self.compositepollthread.stop.set()
            else:
                self.getsession()
            return serverresponse
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN
        

    # join session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   server response or OFFLINE_RETURN on failure to connect

    def joinsession(self, nickname, sessionid):
        try:
            serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text
            if serverresponse == FAILURE_RETURN:
                self.getsession()
            elif serverresponse == SUCCESS_RETURN:
                self.sessionid = sessionid
                self.owner = False
                self.compositepollthread.start()
            return serverresponse
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # leave session (without ending it)
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect
    
    def leavesession(self):
        try:
            serverresponse = requests.post(SERVER_URL + "leavesession", data={'mac' : self.mac}).text
            if serverresponse == SUCCESS_RETURN:
                self.sessionid = None
                self.owner = False
                self.compositepollthread.stop.set()
            return serverresponse
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # update pedal object sessionid & owner variables (without actually returning them)
    # args:     **kwargs to pass to request GET call
    # return:   server response or OFFLINE_RETURN on failure to connect
    
    def getsession(self, **kwargs):
        try:
            serverresponse = requests.post(SERVER_URL + "getsession", data={'mac' : self.mac}, **kwargs).text
            if serverresponse != FAILURE_RETURN:
                if serverresponse == NONE_RETURN:
                    self.sessionid = None
                    self.owner = False
                else:
                    self.sessionid, self.owner = serverresponse.split(":")
                    # convert string description to a boolean
                    self.owner = (self.owner == "owner")
                    return SUCCESS_RETURN
            return serverresponse 
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # updat pedal object sessionmembers list
    # return:       server response or OFFLINE_RETURN on failure to connect

    def getmembers(self):
        try:
            serverresponse = requests.post(SERVER_URL + "getmembers", data={'mac' : self.mac}).text
            if serverresponse == FAILURE_RETURN:
                self.sessionmembers = []
            else:
                self.sessionmembers = serverresponse.split(",")
                return SUCCESS_RETURN
            return serverresponse
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # requests current composite from server
    # args:     timestamp: timestamp of last update
    # returns:  true if updated, false otherwise, OFFLINE_RETURN on failure to connect
    
    def getcomposite(self, timestamp=None):
        try:
            compositeresp = requests.post(SERVER_URL + "getcomposite", data={'mac' : self.mac, 'timestamp' : timestamp})
            if compositeresp.text != NONE_RETURN:
                self.compositedata = compositeresp.content
                return SUCCESS_RETURN
            return FAILURE_RETURN
        except requests.exceptions.ConnectionError:
            return OFFLINE_RETURN

    # ---------------------------
    #   Loop Processing Methods
    # ---------------------------

    # begin recording loop

    def startloop(self):
        self.recording = True
        if self.emptycomposite:
            self.firstrecpass = True
        self.led.turn_on()

    # stop recording loop, add loop data to composite, and send
    # loop to strangeloop server, if pedal is in online session
    # return:   server response if online, SUCCESS_RETURN if offline

    def endloop(self):

        # convenience method to add time-tagged loop b to loop a
        # args:     a: base loop
        #           b: loop to add to base
        #           truncate: whether to discard or include excess from b 
        # return:   2D numpy array representing the combined time-tagged signals

        def mergeloops(a, b, truncate=True):

            # to mix signals, add a[i] to b[i], and subtract average signal value so that b[i] is effectively normalized around 0
            # this is the best mixing solution I could find
            normalfactor = int((np.average(a[0]) + np.average(b[0])) // 2)

            # composite will have a maximum length of len(a) + len(b), if no mixing of signals occurs
            composite = np.zeros((2, a.shape[1] + b.shape[1]), dtype=float)

            ai = bi = ci = 0
            
            while ci < composite.shape[1]:

                # if the base loop array is exhausted, the composite is finished
                if ai >= a.shape[1]:
                    # if we don't truncate b, we'll need to add it to the composite
                    if not truncate:
                        bremain = b.shape[1] - bi
                        composite[:, ci:ci + bremain] = b[:, bi:bi + bremain]
                        ci += bremain
                    break

                # if the added loop array is exhausted, add the rest of the base loop and finish
                elif bi >= b.shape[1]:
                    aremain = a.shape[1] - ai
                    composite[:, ci:ci + aremain] = a[:, ai:ai + aremain]
                    ci += aremain
                    break
 
                # merge a & b samples if they're within an average sample period of each other, otherwise add the first one
                if abs(a[1][ai] - b[1][bi]) < self.avgsampleperiod:
                    composite[0][ci] = a[0][ai] + b[0][bi] - normalfactor
                    composite[1][ci] = (a[1][ai] + b[1][bi]) / 2
                    ai += 1
                    bi += 1
                else:
                    if a[1][ai] < b[1][bi]:
                        composite[:, ci] = a[:, ai] 
                        ai += 1
                    else:
                        composite[:, ci] = b[:, bi] 
                        bi += 1

                ci += 1

            # trim empty excess of composite
            # it's very likely there will be some
            composite = composite[:, :ci]
            return composite

        self.recording = False
        self.led.turn_off()
        time.sleep(END_LOOP_SLEEP)

        # remove allocated but unused array space
        self.loopdata = self.loopdata[:, :self.loopiter]

        # if composite is being written to for the first time, truncate excess allocated space
        if self.emptycomposite:
            self.compositedata = self.compositedata[:, self.loopiter]
            self.emptycomposite = True

        # if pedal in online session, upload json-encoded loop numpy array
        if self.sessionid:
            
            # sort loop array by timecodes before uploading

            # provide device-unique loop index
            loopindex = self.loopindex
            self.loops.append(loopindex)
            self.loopindex += 1
            try:
                serverresponse = requests.post(SERVER_URL + "addtrack", data={'mac' : self.mac, 'index' : loopindex}, files={'wavdata' : StringIO(json.dumps(loopdata.tolist()))}).text
            except requests.exceptions.ConnectionError:
                serverresponse = OFFLINE_RETURN

            # reset loop array, assuming it'll be roughly the same shape as composite
            # ultimately, though, array shape depends on audio sampling rate
            self.loopdata = np.zeros_like(self.compositedata)
            self.loopiter = 0
            
            # apply new composite
            self.getcomposite()
            return serverresponse

        self.loopdata = np.zeros_like(self.compositedata)
        self.loopiter = 0

        return SUCCESS_RETURN

    # remove loop from composite
    # in offline session, only most recent loop is removeable
    # args:     index:  device-unique id for loop to be removed (online only)
    # return:   server response (or SUCCESS_RETURN for offline session)

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
            if self.compositedata is None:
                    self.emptycomposite = True
            return SUCCESS_RETURN
