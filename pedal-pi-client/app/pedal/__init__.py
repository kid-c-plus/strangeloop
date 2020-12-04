import uuid
import json
import requests
import time
import atexit
from threading import Thread, Event, Lock
from datetime import datetime
from io import BytesIO
import numpy as np
from . import rpi
import logging

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
RPI_POLL_INTERVAL = 0.01
COMPOSITE_POLL_INTERVAL = 2

# loops can be up to 2 minutes long
MAX_LOOP_DURATION = 120

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

# defaults for all the keyword args that can be passed to the Pedal constructor
# germane to both the Pedal and the various thread subclasses, but all accessed through the parent Pedal object
PEDAL_KW_DEFAULTS = {

    # Pedal object variables
    'debug'     : False,
    'webdebug'  : False,

    # AudioProcessingThread object variables

    # load input from file instead of reading from AUX input
    'audioloadinput'    : False,
    'audioinfile'       : "/opt/strangeloop/pedal-pi-client/app/pedal/debug.in",

    # save output
    'audiosaveoutput'   : False,
    'audiooutfile'      : "/opt/strangeloop/pedal-pi-client/app/pedal/debug-%s.out" % datetime.utcnow().strftime("%Y-%m-%d-%H:%M:%S"),

    # write output to AUX output
    'audioplayoutput'   : True
}

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
            self.timestamp = datetime.utcnow().timestamp()

            logging.debug("Initialized composite polling thread")

        # main thread execution loop

        def run(self):

            logging.debug("Started composite polling thread")

            while self.pedal.running: 
                time.sleep(COMPOSITE_POLL_INTERVAL)

                # timestamp to determine whether any new data needs to be downloaded
                if not self.pedal.recording and self.pedal.getcomposite(timestamp=self.timestamp):
                    self.timestamp = datetime.utcnow().timestamp()

                    logging.debug("Downloaded new composite at %s" % self.timestamp.strftime("%Y-%m-%d-%H:%M:%S"))

            logging.debug("Ended composite polling thread")


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

            # load input from file
            if pedal.audioloadinput:
                self.audioinfileobj = open(pedal.audioinfile, mode="r")

            # save output to file
            if pedal.audiosaveoutput:
                self.audiooutfileobj = open(pedal.audiooutfile, mode="w")

            logging.debug("Initialized audio processing thread")

        # main thread execution loop

        def run(self):

            logging.debug("Started audio processing thread")

            # simple helper method to append whitespace to array
            # return: new array with whitespace appended
            def extendarray(arr):
                return np.append(arr, np.zeros((int(ARRAY_SIZE_SEC / self.pedal.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE))

            # simple helper to read a single number out of a file of space-separated numbers
            def readnum(fileobj):
                retnum = ""
                while True:
                    char = fileobj.read(1)
                    if not char or char == "" or char == " ":
                        break
                    retnum += char
                try:
                    return int(retnum)
                except ValueError:
                    logging.error("AudioProcessingThread: invalid character string %d in input file %d" % (retnum, self.pedal.audioinfile))
                    return 0

            # initialize values for composite iteration & timestamp calculation
            # compositepassstart: timestamp when the composite loop was last started or restarted
            # looprecstart: timestamp of the beginning of loop recording
            #               (only used when composite is empty. otherwise, all loop timestamp data
            #               is stored relative to the compositepassstart timestamp)
            compositeindex = lastcompositeindex = compositepassstart = looprecstart = 0

            while self.pedal.running:

                # current timestamp
                passtime = time.time()

                # used for diagnostics (specifically calculating sampling frequency)
                self.monitors += 1

                # update average cycle period every 100 cycles
                # this is a pedal property because it's useful to know when appending to loop & composite arrays
                if not self.monitors % 100:
                    self.pedal.avgsampleperiod = (passtime - self.uptime) / self.monitors

                # determines whether some debug information is printed
                debugpass = not (self.monitors - 1) % 100000

                if self.pedal.monitoring:

                    # read from input file (for unit testing)
                    if self.pedal.audioloadinput:
                        inputbits = readnum(self.audioinfileobj)

                    # read from AUX input
                    else:
                        inputbits = self.pedal.audioin.read()

                    outputbits = inputbits

                    # no composite loop data to play
                    if self.pedal.emptycomposite:

                        # reset composite-related variables
                        compositeindex = lastcompositeindex = compositepassstart = 0

                        if self.pedal.recording:

                            # lock to protect loop array
                            with self.pedal.looplock:

                                # if looprecstart is zero, this is the first recording pass
                                if not looprecstart:
                                    looprecstart = passtime

                                looprectimestamp = passtime - looprecstart

                                # don't record past maximum loop length
                                if looprectimestamp < MAX_LOOP_DURATION:

                                    # loop length is unbounded. add 10 seconds to loop np array
                                    if self.pedal.loopindex >= len(self.pedal.loopdata):
                                        self.pedal.loopdata = extendarray(self.pedal.loopdata)

                                    # composite is also unbound on first loop
                                    if self.pedal.loopindex >= len(self.pedal.compositedata):
                                        self.pedal.compositedata = extendarray(self.pedal.compositedata)

                                    # save input to both composite and loopdata array to upload to server
                                    # store timestamp relative to composite playback head, and sort array by timestamps before submitting
                                    self.pedal.loopdata[self.pedal.loopindex] = self.pedal.compositedata[self.pedal.loopindex] = (inputbits, looprectimestamp)
                                    self.pedal.loopindex += 1

                                    if debugpass:
                                        logging.debug("AudioProcessingThread: Recorded audio to first loop: %d" % inputbits)
                        else:

                            # reset first loop record variable
                            looprecstart = 0

                    else:

                        # lock to protect composite array
                        with self.pedal.compositelock:

                            # compositepassstart of zero indicates this is the first pass where composite will be played 
                            # if playback & recording have reached the end of the composite, return to the start, and note the time new playback began
                            if not compositepassstart or compositeindex >= len(self.pedal.compositedata) - 1:
                                compositeindex = 0
                                compositepassstart = passtime

                            # playback timestamp relative to the start of the composite
                            inputtimestamp = passtime - compositepassstart

                            # search in the composite for the closest timestamps higher and lower than the current timestamp (relative to composite start time)
                            # could use binary search, but in practice this should be within a small number of array indices away from the current composite index
                            # each time, as long as sampling rate stays constant. so, though the worst-case big-o of this is worse, it'll perform better on average

                            while compositeindex < len(self.pedal.compositedata) - 1 and inputtimestamp > self.pedal.compositedata[compositeindex + 1]['timestamp']:
                                compositeindex += 1 

                            # play & write to the closer of the two samples adjoining the current timestamp (or the index sample if the index is at the end of the array)
                            compositeindex = compositeindex if (compositeindex == len(self.pedal.compositedata) - 1 or inputtimestamp - self.pedal.compositedata[compositeindex]['timestamp'] <= self.pedal.compositedata[compositeindex + 1]['timestamp'] - inputtimestamp) else compositeindex + 1

                            compositebits = self.pedal.compositedata[compositeindex]['value']

                            # merge input and output bits by adding them and subtracting the mean of the composite array
                            outputbits = inputbits + compositebits - self.pedal.compositenorm

                            if self.pedal.recording:

                                with self.pedal.looplock:

                                    # add merged input and composite, and average timestamps of composite recording and current input
                                    # write to all indices between the last written one and this one
                                    # which will result in some pretty square sonic waves, but it's better than having composite array
                                    # indices that aren't written to by subsequent loops
                                    if lastcompositeindex <= compositeindex:
                                        self.pedal.compositedata[lastcompositeindex + 1 : compositeindex + 1] = (outputbits, (inputtimestamp + self.pedal.compositedata[compositeindex]['timestamp']) / 2)
                                    # if the composite index looped around since last pass
                                    # even if the compositedata array has changed size since the last pass, and lastcompositeindex is larger
                                    # than the end of the array, this won't throw an error, it'll just only write the [ : compositeindex + 1] piece
                                    else:
                                        self.pedal.compositedata[lastcompositeindex + 1 : ] = self.pedal.compositedata[ : compositeindex + 1] = (outputbits, (inputtimestamp + self.pedal.compositedata[compositeindex]['timestamp']) / 2)

                                    lastcompositeindex = compositeindex

                                    if debugpass:
                                        logging.debug("AudioProcessingThread: recorded audio to loop number %d: %d" % (len(self.pedal.loops), inputbits))

                                    # loop length is unbounded. add 10 seconds to loop np array
                                    if self.pedal.loopindex >= len(self.pedal.loopdata):
                                        self.pedal.loopdata = extendarray(self.pedal.loopdata)

                                    # save input to loopdata array to upload to server
                                    # store timestamp relative to composite playback head, and sort array by timestamps before submitting
                                    self.pedal.loopdata[self.pedal.loopindex] = (inputbits, inputtimestamp)
                                    self.pedal.loopindex += 1

                    # write to AUX output
                    if self.pedal.audioplayoutput:
                        self.pedal.audioout.write(outputbits)

                    # save to output file
                    if self.pedal.audiosaveoutput:
                        try:
                            self.audiooutfile.write("%d " % outputbits)
                        except:
                            pass

            logging.debug("Ended audio processing thread")

        # process end functions, mostly debugging

        def end(self):

            totaltime = time.time() - self.uptime
            logging.info("AudioProcessingThread: monitoring frequency: %f Hz" % (self.monitors / totaltime))

            if self.pedal.audiosaveoutput:
                self.audiooutfile.close()

            logging.debug("Deinitialized audio processing thread")

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

            logging.debug("Initialized RPi Polling Thread")

        # main thread execution loop

        def run(self):

            logging.debug("Started RPi Polling Thread")
            
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
                if pushbutton1_val == PUSHBUTTON_PRESS and not self.pedal.emptycomposite and not self.pedal.recording:
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

            logging.debug("Ended RPi Polling Thread")

    # Pedal constructor class
    # args:     **kwargs: override PEDAL_KW_DEFAULTS above

    def __init__(self, **kwargs):

        logging.info("Initializing Pedal object")

        # set object properties
        self.__dict__.update(PEDAL_KW_DEFAULTS)

        # only override the keyword arguments that appear in the PEDAL_KW_DEFAULTS dict
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in list(PEDAL_KW_DEFAULTS.keys()))

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

        # assume 41 kHz sampling interval
        self.avgsampleperiod = 1 / 41000

        # initialize empty loop data ~ 10 seconds long
        self.loopdata = np.zeros((int(ARRAY_SIZE_SEC / self.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE)
        self.loopindex = 0

        # initialize composite data and average value (zero to start), used for layering loops on top of the composite 
        self.compositedata = np.zeros((int(ARRAY_SIZE_SEC / self.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE)
        self.compositenorm = 0
        self.lastcomposite = None

        # track whether composite, and previous composite, have been recorded to before or not
        self.emptycomposite = self.emptylastcomposite = True

        # initialize process threads
        self.compositepollthread    = Pedal.CompositePollingThread(pedal=self)
        self.processaudiothread     = Pedal.AudioProcessingThread(pedal=self)
        self.monitorrpithread       = Pedal.RPiMonitoringThread(pedal=self)

        # process thread flags
        self.running = True
        self.monitoring = False
        self.recording = False

        # mutexes to protect writing to loop & composite array between threads
        self.looplock = Lock()
        self.compositelock = Lock()

        # when online, the user can delete loops by index
        # thus, it's not enough merely to track the number of loops
        # each one has a unique id on the server consisting of "MAC address:loop index"
        # the index iterates with each new loop and does not decrease on loop deletion
        self.loops = []

        # start process threads
        self.processaudiothread.start()
        self.monitorrpithread.start()

        if self.webdebug:
            print(self.newsession("rick"))

        self.led.turn_off()

        logging.info("Initialized Pedal object")

    # destructor method
    # set end flag so threads can exit gracefully

    def end(self):

        logging.info("Deinitializing Pedal object")

        self.running = False

        # call process audio destructor
        if self.processaudiothread:
            self.processaudiothread.end()

        self.led.turn_off()

        logging.info("Deinitialized Pedal object")

    # ------------------------------
    #   Server Interaction Methods
    # ------------------------------

    # create new session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   newly created session identifier on success, server response on failure, or OFFLINE_RETURN on failure to connect

    def newsession(self, nickname):
        try:
            logging.info("Creating new session")

            serverresponse = requests.post(SERVER_URL + "newsession", data={'mac' : self.mac, 'nickname' : nickname}, **requestargs).text
            
            logging.info("New session creation returned %s" % serverresponse)

            if serverresponse == FAILURE_RETURN:
                self.getsession()

            elif serverresponse != NONE_RETURN and serverresponse != FULL_RETURN:
                self.sessionid = serverresponse 
                self.owner = True
                self.compositepollthread.start()
                return SUCCESS_RETURN
            
            return serverresponse
        
        except requests.exceptions.ConnectionError:

            logging.info("New session creation failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # end session
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect

    def endsession(self):
        try: 
            logging.info("Ending session %s" % self.sessionid if self.sessionid else "None")

            serverresponse = requests.post(SERVER_URL + "endsession", data={'mac' : self.mac}).text

            logging.info("Session end returned %s" % serverresponse)

            if serverresponse == SUCCESS_RETURN:
                self.sessionid = None
                self.owner = False
                self.compositepollthread.stop.set()
            else:
                self.getsession()
            return serverresponse
        except requests.exceptions.ConnectionError:

            logging.info("Session end failed. Unable to connect to server")  
            return OFFLINE_RETURN


    # join session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   server response or OFFLINE_RETURN on failure to connect

    def joinsession(self, nickname, sessionid):
        try:
            logging.info("Joining session %s" % sessionid)

            serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text

            logging.info("Session join returned %s" % serverresponse)

            if serverresponse == FAILURE_RETURN:
                self.getsession()
            elif serverresponse == SUCCESS_RETURN:
                self.sessionid = sessionid
                self.owner = False
                self.compositepollthread.start()
            return serverresponse
        except requests.exceptions.ConnectionError:

            logging.info("Session join failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # leave session (without ending it)
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect

    def leavesession(self):
        try:
            logging.info("Leaving session %s" % self.sessionid if self.sessionid else "None")

            serverresponse = requests.post(SERVER_URL + "leavesession", data={'mac' : self.mac}).text

            logging.info("Session leave returned %s" % serverresponse)

            if serverresponse == SUCCESS_RETURN:
                self.sessionid = None
                self.owner = False
                self.compositepollthread.stop.set()
            return serverresponse
        except requests.exceptions.ConnectionError:

            logging.info("Leave session failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # update pedal object sessionid & owner variables (without actually returning them)
    # args:     **kwargs to pass to request GET call
    # return:   server response or OFFLINE_RETURN on failure to connect

    def getsession(self, **kwargs):
        try:
            logging.info("Refreshing session")

            serverresponse = requests.post(SERVER_URL + "getsession", data={'mac' : self.mac}, **kwargs).text

            logging.info("Session refresh returned %s" % serverresponse)

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

            logging.info("Session refresh failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # updat pedal object sessionmembers list
    # return:       server response or OFFLINE_RETURN on failure to connect

    def getmembers(self):
        try:
            logging.info("Refreshing member list")

            serverresponse = requests.post(SERVER_URL + "getmembers", data={'mac' : self.mac}).text

            logging.info("Member list refresh returned %s" % serverresponse)

            if serverresponse == FAILURE_RETURN:
                self.sessionmembers = []
            else:
                self.sessionmembers = serverresponse.split(",")
                return SUCCESS_RETURN
            return serverresponse
        except requests.exceptions.ConnectionError:

            logging.info("Member list refresh failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # requests current composite from server 
    # args:     timestamp: timestamp of last update
    # returns:  true if updated, false otherwise, OFFLINE_RETURN on failure to connect

    def getcomposite(self, timestamp=None):
        try:
            logging.info("Downloading composite for timestamp %s" % timestamp.strftime("%Y-%m-%d-%H:%M:%S") if timestamp else "None")

            compositeresp = requests.post(SERVER_URL + "getcomposite", data={'mac' : self.mac, 'timestamp' : timestamp})

            logging.info("Composite download returned %s" % serverresponse)
            if compositeresp.text != NONE_RETURN:
                with self.compositelock:
                    self.compositedata = np.load(BytesIO(compositeresp.content))
                    # compute new input norm for adding subsequent input
                    self.compositenorm = np.mean(self.compositedata[:]['value'], dtype=int)
                return SUCCESS_RETURN
            return FAILURE_RETURN
        except requests.exceptions.ConnectionError:

            logging.info("Composite download failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # ---------------------------
    #   Loop Processing Methods
    # ---------------------------

    # begin recording loop

    def startloop(self):
        self.recording = True

        # store previous composite data in lastcomposite variable
        with self.compositelock:
            self.lastcomposite = np.copy(self.compositedata)
            self.emptylastcomposite = self.emptycomposite

        self.led.turn_on()

    # stop recording loop, add loop data to composite, and send
    # loop to strangeloop server, if pedal is in online session
    # return:   server response if online, SUCCESS_RETURN if offline

    def endloop(self):

        self.recording = False
        self.led.turn_off()
        time.sleep(END_LOOP_SLEEP)

        # mutexes for writing to shared loop & composite arrays
        with self.looplock and self.compositelock:

            # remove allocated but unused array space
            self.loopdata = self.loopdata[:self.loopindex]

            # if composite is being written to for the first time, truncate excess allocated space
            if self.emptycomposite:
                self.compositedata = self.compositedata[:self.loopindex]
                self.emptycomposite = False

            # compute new input norm for adding subsequent input
            self.compositenorm = np.mean(self.compositedata[:]['value'], dtype=int)

            # provide device-unique loop index
            loopindex = max(self.loops) + 1 if len(self.loops) else 0
            self.loops.append(loopindex)

            # if pedal in online session, upload json-encoded loop numpy array
            if self.sessionid:

                # sort loop array by timecodes before uploading
                self.loopdata.sort(order="timecode")

                 # write returnaudio numpy array to a virtual bytes file, and then save the bytes output
                loopfile = BytesIO()
                np.save(loopfile, self.loopdata)

                try:
                    logging.info("Uploading loop %d to session %s" % (loopindex, self.sessionid if self.sessionid else None))

                    serverresponse = requests.post(SERVER_URL + "addtrack", data={'mac' : self.mac, 'index' : loopindex}, files={'npdata' : loopfile}).text

                    logging.info("Loop upload returned %d" % serverresponse)

                except requests.exceptions.ConnectionError:

                    logging.info("Loop upload failed. Unable to connect to server")  
                    serverresponse = OFFLINE_RETURN

                # reset loop array, assuming it'll be roughly the same shape as composite
                # ultimately, though, array shape depends on audio sampling rate
                self.loopdata = np.zeros_like(self.compositedata)
                self.loopindex = 0

                # apply new composite
                self.getcomposite()
                return serverresponse

            self.loopdata = np.zeros_like(self.compositedata)
            self.loopindex = 0

            return SUCCESS_RETURN

    # remove loop from composite
    # in offline session, only most recent loop is removeable
    # args:     index:  device-unique id for loop to be removed (online only)
    # return:   server response (or SUCCESS_RETURN for offline session)

    def removeloop(self, index=None):
        with self.compositelock:
            if self.sessionid:
                if index:
                    if index in self.loops:
                        logging.info("Removing loop %d from session %s" % (index, self.sessionid))

                        serverresponse = requests.post(SERVER_URL + "removetrack", data={'mac' : self.mac, 'index' : index}).text
                        
                        logging.info("Loop removal returned %s" % serverresponse)

                        if serverresponse == SUCCESS_RETURN:
                            self.loops.pop(self.loops.index(index))
                        
                        self.getcomposite()
                        return serverresponse
                    else:
                        return FAILURE_RETURN
                elif len(self.loops) > 1:
                    logging.info("Removing most recent loop %d from session %s" % (max(self.loops), self.sessionid))

                    serverresponse = requests.post(SERVER_URL + "removetrack", data={'mac' : self.mac, 'index' : max(self.loops)}).text

                    logging.info("Loop removal returned %s" % serverresponse)

                    if serverresponse == SUCCESS_RETURN:
                        self.loops.pop(self.loops.index(max(self.loops)))
                    
                    self.getcomposite()
                    return serverresponse
            else:
                # can only erase most recent loop if using without web session
                if self.lastcomposite is not None:
                    logging.info("Removing most recent loop from offline session")

                    self.compositedata = np.copy(self.lastcomposite)
                else:
                    self.compositedata = np.zeros((int(ARRAY_SIZE_SEC / self.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE)

                self.emptycomposite = self.emptylastcomposite
                return SUCCESS_RETURN
