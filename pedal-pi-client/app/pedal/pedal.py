# -------------------------------------------------------------------------
#   Pedal class definition - flask app recieves an instance of this class
# -------------------------------------------------------------------------

import uuid
import socket
import json
import requests
import time
import atexit
import threading
import multiprocessing
import signal
from datetime import datetime as dt
from io import BytesIO
import numpy as np
import logging

from common import *

from . import rpi, vrpi, audioprocessor

# -------------
#   Constants
# -------------

SERVER_URL = "http://192.168.1.72:5000/"

END_LOOP_SLEEP = 0.0

# delays to pause between execution of Raspberry Pi and strangeloop server monitoring threads
RPI_POLL_INTERVAL = 0.01
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

# defaults for all the keyword args that can be passed to the Pedal constructor
# germane to both the Pedal and the various thread subclasses, but all accessed through the parent Pedal object
PEDAL_KW_DEFAULTS = {

    # Pedal object variables
    'debug'         : False,
    'createsession'      : False,
    # default is to use root-level logger
    'loggername'    : None,

    'rpisleep'      : RPI_POLL_INTERVAL,

    # use virtual rpi queues instead of true RPi components
    'virtualize'    : False,
    'vqueues'       : {
                        'pushbutton1'   : None,
                        'pushbutton2'   : None,
                        'toggleswitch'  : None,
                        'footswitch'    : None,
                        'led'           : None
                      },

    # subdict to pass to AudioProcessor process
    'apargs'        : {}
}

# -----------
#   Classes
# -----------

# ------------------------------------------------------------------------------
#   Pedal - class handling all the basic functionality of a looper pedal
#           the Flask UI receives and interacts with an instance of this class
# ------------------------------------------------------------------------------

class Pedal():
    
    # ----------------------------------------------------------------
    #   ProcessLoggingThread - Thread superclass that reads input
    #                          from process queue and logs it to the
    #                          pedal logger in a safe way
    # ----------------------------------------------------------------

    class ProcessLoggingThread(threading.Thread):
        def __init__(self, pedal, logqueue):
            threading.Thread.__init__(self)
            self.pedal = pedal
            self.logqueue = logqueue

            self.pedal.slplogger.debug("Initialized process logging thread")

        def run(self):
        
            self.pedal.slplogger.debug("Started process logging thread")

            while self.pedal.running or not self.logqueue.empty():

                # block until messagae is avaliable
                level, message = self.logqueue.get()
                self.pedal.slplogger.log(getattr(logging, level), message)


    # ----------------------------------------------------------------
    #   CompositePollingThread - Thread superclass that periodically 
    #                            polls strangeloop server for new 
    #                            additions to the composite loop
    # ----------------------------------------------------------------

    class CompositePollingThread(threading.Thread):

        # overloaded Thread constructor
        # args:     pedal: parent Pedal object that instantiated this thread

        def __init__(self, pedal):
            threading.Thread.__init__(self)
            self.stop = threading.Event()
            self.pedal = pedal
            self.timestamp = None

            self.pedal.slplogger.debug("Initialized composite polling thread")

        # main thread execution loop

        def run(self):

            self.pedal.slplogger.debug("Started composite polling thread")

            while self.pedal.running: 
                time.sleep(COMPOSITE_POLL_INTERVAL)

                # timestamp to determine whether any new data needs to be downloaded
                if not self.stop.is_set() and not self.pedal.recording and not self.pedal.playing and self.pedal.getcomposite(timestamp=self.timestamp) == SUCCESS_RETURN:
                    self.timestamp = dt.utcnow().timestamp()

                    self.pedal.slplogger.debug("Downloaded new composite at %s" % dt.utcfromtimestamp(self.timestamp).strftime("%Y-%m-%d-%H:%M:%S"))

            self.pedal.slplogger.debug("Ended composite polling thread")


    # ---------------------------------------------------------------------
    #   RPiMonitoringThread - Thread superclass to monitor RPi components 
    #                       and change pedal state accordingly
    # ---------------------------------------------------------------------

    class RPiMonitoringThread(threading.Thread):

        # overloaded Thread constructor
        # args:     pedal: parent Pedal object that instantiated this thread

        def __init__(self, pedal):
            threading.Thread.__init__(self)
            self.pedal = pedal

            self.pedal.slplogger.debug("Initialized RPi Polling Thread")

        # main thread execution loop

        def run(self):

            self.pedal.slplogger.debug("Started RPi Polling Thread")

            looprecstart = 0
            
            while self.pedal.running:
                time.sleep(self.pedal.rpisleep)

                # button reads are unreliable for a little while after a press
                debounce_delay = False

                pushbutton1_val     = self.pedal.pushbutton1.read()
                pushbutton2_val     = self.pedal.pushbutton2.read()
                toggleswitch_val    = self.pedal.toggleswitch.read()
                footswitch_val      = self.pedal.footswitch.read()

                # pedal functions are only available when pedal is in monitor mode
                if footswitch_val == FOOTSWITCH_MON and not self.pedal.monitoring:
                    self.pedal.slplogger.info("Footswitch set to monitor mode")
                    self.pedal.audiocontrolqueue.put(audioprocessor.Control.ToggleMonitoring)
                    self.pedal.monitoring = True
                    debounce_delay = True

                # in bypass mode, the pedal can neither read from input nor write to output
                elif footswitch_val == FOOTSWITCH_BYPASS and self.pedal.monitoring:
                    self.pedal.slplogger.info("Footswitch set to bypass mode")
                    self.pedal.audiocontrolqueue.put(audioprocessor.Control.ToggleMonitoring)
                    self.pedal.monitoring = False
                    if self.pedal.recording:
                        self.pedal.endloop()
                    debounce_delay = True

                # you can only remove a loop if you aren't currently recording one
                if pushbutton1_val == PUSHBUTTON_PRESS and not self.pedal.recording:
                    self.pedal.slplogger.info("Loop removed")
                    self.pedal.removeloop()
                    debounce_delay = True

                # start loop
                if pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and not self.pedal.recording and not self.pedal.playing:
                    self.pedal.slplogger.info("Loop started")
                    # store timestamp when loop started so that recording can time out after 2 minutes
                    looprecstart
                    self.pedal.startloop()
                    debounce_delay = True

                # end loop on loop button press or recording timeout
                elif (pushbutton2_val == PUSHBUTTON_PRESS and footswitch_val == FOOTSWITCH_MON and self.pedal.recording) or (self.pedal.recording and dt.utcnow().timestamp() - looprecstart > MAX_LOOP_TIME):
                    self.pedal.slplogger.info("Loop ended")
                    self.pedal.endloop()
                    debounce_delay = True

                if debounce_delay:
                    rpi.debounce_delay()

            self.pedal.slplogger.debug("Ended RPi Polling Thread")

    # Pedal constructor class
    # args:     **kwargs: override PEDAL_KW_DEFAULTS above

    def __init__(self, **kwargs):

        # set object properties
        self.__dict__.update(PEDAL_KW_DEFAULTS)

        # only override the keyword arguments that appear in the PEDAL_KW_DEFAULTS dict
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in list(PEDAL_KW_DEFAULTS.keys()))

        # flask logger to use
        self.slplogger = logging.getLogger(self.loggername)

        self.slplogger.info("Initializing Pedal object")

        if self.virtualize:

            self.pushbutton1    = vrpi.GPIO(self.vqueues['pushbutton1'], vrpi.GPIO.FSEL.INPUT, PUSHBUTTON_RELEASE)
            self.pushbutton2    = vrpi.GPIO(self.vqueues['pushbutton2'], vrpi.GPIO.FSEL.INPUT, PUSHBUTTON_RELEASE)
            self.toggleswitch   = vrpi.GPIO(self.vqueues['toggleswitch'], vrpi.GPIO.FSEL.INPUT, TOGGLESWITCH_OFF)
            self.footswitch     = vrpi.GPIO(self.vqueues['footswitch'], vrpi.GPIO.FSEL.INPUT, FOOTSWITCH_MON)
            self.led            = vrpi.GPIO(self.vqueues['led'], vrpi.GPIO.FSEL.OUTPUT)

        else:

            self.pushbutton1    = rpi.GPIO(PUSHBUTTON1, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
            self.pushbutton2    = rpi.GPIO(PUSHBUTTON2, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
            self.toggleswitch   = rpi.GPIO(TOGGLESWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
            self.footswitch     = rpi.GPIO(FOOTSWITCH, rpi.GPIO.FSEL.INPUT, rpi.GPIO.PUD.UP)
            self.led            = rpi.GPIO(LED, rpi.GPIO.FSEL.OUTPUT)

        self.led.turn_on()

        # device MAC address is used as unique id in server interactions
        uuidnode = uuid.getnode()
        self.mac = ':'.join(("%012X" % uuidnode)[i:i+2] for i in range(0, 12, 2))

        # recieve device domain name on local network for AJAX callbacks in flask
        # recieve IP for flask CORS config
        self.domainname = socket.getfqdn()
    
        testconnection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        testconnection.connect(("8.8.8.8", 80))
        self.ipaddress = testconnection.getsockname()[0]

        self.sessionid = None
        self.owner = False
        self.sessionmembers = None

        # assume 41 kHz sampling interval
        self.avgsampleperiod = 1 / 41000

        # initialice IPC threads for audioprocessor
        self.audiocontrolqueue      = multiprocessing.Queue()
        self.audiocompositequeue    = multiprocessing.Queue()
        self.audioloopqueue         = multiprocessing.Queue()
        self.audiologqueue          = multiprocessing.Queue()

        # initialize process threads
        self.processlogthread       = Pedal.ProcessLoggingThread(pedal=self, logqueue=self.audiologqueue)
        self.compositepollthread    = Pedal.CompositePollingThread(pedal=self)
        self.monitorrpithread       = Pedal.RPiMonitoringThread(pedal=self)
        self.audioprocess           = multiprocessing.Process(target=audioprocessor.run, args=(self.audiocontrolqueue, self.audiocompositequeue, self.audioloopqueue, self.audiologqueue, self.apargs))

        # process thread flags
        self.running = True
        self.monitoring = False
        self.recording = False
    
        # currently playing back only one loop instead of the composite
        self.playing = False
        self.playbackloopindex = 0

        # store a local dict of all loops made on this pedal, so that they can be uploaded individually
        self.loops = {}

        # do not start composite polling thread until pedal goes online
        self.compositepollstarted = False

        self.led.turn_off()

        self.slplogger.info("Initialized Pedal object")

    # begin pedal threads

    def run(self):    

        # start process threads
        self.processlogthread.start()
        self.monitorrpithread.start()

        # child process will inherit "ignore SIGINT", so that it can be exited gracefully from parent process
        # from: https://stackoverflow.com/questions/11312525/catch-ctrlc-sigint-and-exit-multiprocesses-gracefully-in-python
        originalsiginthandler = signal.signal(signal.SIGINT, signal.SIG_IGN)

        # initialize audio processor and necessary queues, and then run
        self.audioprocess.start()

        # restore previous SIGINT handler
        signal.signal(signal.SIGINT, originalsiginthandler)        

        # check initial session membership
        sessionresp = self.getsession(timeout=1)

        if self.createsession:
            self.slplogger.info("Creating new session: %s" % self.newsession("rick"))

    # destructor method
    # set end flag so threads can exit gracefully

    def end(self):

        self.slplogger.info("Deinitializing Pedal object")

        self.running = False

        # call process audio destructor
        if self.audioprocess:
            self.audiocontrolqueue.put(audioprocessor.Control.EndProcess)
            self.audioprocess.join()

        self.led.turn_off()

        self.slplogger.info("Deinitialized Pedal object")

    # --------------------------------
    #   Session Manipulation Methods
    # --------------------------------

    # create new session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   server response or OFFLINE_RETURN on failure to connect

    def newsession(self, nickname):
        try:
            self.slplogger.info("Creating new session")

            serverresponse = requests.post(SERVER_URL + "newsession", data={'mac' : self.mac, 'nickname' : nickname}).text
            
            self.slplogger.info("New session creation returned %s" % serverresponse)

            self.getsession()

            return serverresponse
        
        except requests.exceptions.ConnectionError:

            self.slplogger.info("New session creation failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # end session
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect

    def endsession(self):
        try: 
            self.slplogger.info("Ending session %s" % self.sessionid if self.sessionid else "None")

            serverresponse = requests.post(SERVER_URL + "endsession", data={'mac' : self.mac}).text

            self.slplogger.info("Session end returned %s" % serverresponse)

            self.getsession()

            return serverresponse

        except requests.exceptions.ConnectionError:

            self.slplogger.info("Session end failed. Unable to connect to server")  
            return OFFLINE_RETURN


    # join session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   server response or OFFLINE_RETURN on failure to connect

    def joinsession(self, nickname, sessionid):
        try:
            self.slplogger.info("Joining session %s" % sessionid)

            serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text

            self.slplogger.info("Session join returned %s" % serverresponse)

            self.getsession()

            return serverresponse
        except requests.exceptions.ConnectionError:

            self.slplogger.info("Session join failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # leave session (without ending it)
    # updates pedal object sessionid & owner variables
    # return:   server response or OFFLINE_RETURN on failure to connect

    def leavesession(self):
        try:
            self.slplogger.info("Leaving session %s" % self.sessionid if self.sessionid else "None")

            serverresponse = requests.post(SERVER_URL + "leavesession", data={'mac' : self.mac}).text

            self.slplogger.info("Session leave returned %s" % serverresponse)

            self.getsession()
        
            return serverresponse
        except requests.exceptions.ConnectionError:

            self.slplogger.info("Leave session failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # ---------------------------------
    #   Server Database Query Methods
    # ---------------------------------

    # update pedal object sessionid & owner variables (without actually returning them)
    # args:     **kwargs to pass to request GET call
    # return:   server response or OFFLINE_RETURN on failure to connect

    def getsession(self, **kwargs):
        try:
            self.slplogger.info("Refreshing session")

            serverresponse = requests.post(SERVER_URL + "getsession", data={'mac' : self.mac}, **kwargs).text

            self.slplogger.info("Session refresh returned %s" % serverresponse)

            if serverresponse != FAILURE_RETURN:
                if serverresponse == NONE_RETURN:
                    if self.sessionid:
                        self.gooffline()
                else:
                    newsessionid, self.owner = serverresponse.split(":")
                    # convert string description to a boolean
                    self.owner = (self.owner == "owner")

                    if not self.sessionid or self.sessionid != newsessionid:
                        self.sessionid = newsessionid
                        self.goonline()

                return SUCCESS_RETURN
            return serverresponse 
        except requests.exceptions.ConnectionError:

            self.slplogger.info("Session refresh failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # update pedal object sessionmembers list
    # return:   server response or OFFLINE_RETURN on failure to connect

    def getmembers(self):
        try:
            self.slplogger.info("Refreshing member list")

            serverresponse = requests.post(SERVER_URL + "getmembers", data={'mac' : self.mac}).text

            self.slplogger.info("Member list refresh returned %s" % serverresponse)

            if serverresponse in [NONE_RETURN, FAILURE_RETURN]:
                self.sessionmembers = []
            else:
                self.sessionmembers = serverresponse.split(",")
                return SUCCESS_RETURN
            return serverresponse
        except requests.exceptions.ConnectionError:

            self.slplogger.info("Member list refresh failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # reconcile online loop collection with offline activity
    # return:   SUCCESS_RETURN on successful reconciliation, FAILURE_RETURN on >=1 failure or OFFLINE_RETURN on failure to connect

    def updateloops(self):
        try:
            self.slplogger.info("Reconciling online loops with offline loops")

            serverresponse = requests.post(SERVER_URL + "getloopids", data={'mac' : self.mac}).text

            self.slplogger.info("Loop id list refresh returned %s" % serverresponse)

            if len(serverresponse) and serverresponse not in [NONE_RETURN, FAILURE_RETURN]:
                try:
                    onlineloopindices = [int(loopid) for loopid in serverresponse.split(",")]

                    updateresponse = SUCCESS_RETURN

                    for onlineloopindex in onlineloopindices:
                        # delete all loops not present or different from offline dict, and upload local loops in those indices
                        if onlineloopindex not in self.loops or not np.array_equal(self.getloop(onlineloopindex), self.loops[onlineloopindex]):
                            if self.removeloop(onlineloopindex) != SUCCESS_RETURN or self.uploadloop(onlineloopindex) != SUCCESS_RETURN:
                                updateresponse = FAILURE_RETURN

                    # upload all loops not present in online session
                    for offlineloopindex in [index for index in self.loops.keys() if index not in onlineloopindices]:
                        if self.uploadloop(offlineloopindex) != SUCCESS_RETURN:
                            updateresponse = FAILURE_RETURN

                    return updateresponse
    
                except ValueError:
                    self.slplogger.error("Invalid loop id data from server")
                    return FAILURE_RETURN

        except requests.exceptions.ConnectionError:

            self.slplogger.info("Loop reconciliation failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # requests current composite from server 
    # args:     timestamp: timestamp of last update
    # returns:  SUCCESS_RETURN if updated, NONE_RETURN otherwise, OFFLINE_RETURN on failure to connect

    def getcomposite(self, timestamp=None):
        try:
            self.slplogger.info("Downloading composite for timestamp %s" % (dt.utcfromtimestamp(timestamp).strftime("%Y-%m-%d-%H:%M:%S") if timestamp else "None"))

            serverresponse = requests.post(SERVER_URL + "getcomposite", data={'mac' : self.mac, 'timestamp' : timestamp})

            self.slplogger.info("Downloaded new composite: %s" % str(serverresponse.text[:min(10, len(serverresponse.text))]))

            if serverresponse.text not in [NONE_RETURN, FAILURE_RETURN] and serverresponse.content:
                if serverresponse.text == EMPTY_RETURN:
                    self.audiocompositequeue.put(None)
                    return SUCCESS_RETURN
                else:
                    try:
                        self.audiocompositequeue.put(np.load(BytesIO(serverresponse.content), allow_pickle=False))
                        return SUCCESS_RETURN
                    except ValueError:
                        self.slplogger.error("Server returned invalid composite numpy array: %s" % serverresponse[: min(100, len(serverresponse))])

            return FAILURE_RETURN

        except requests.exceptions.ConnectionError:

            self.slplogger.info("Composite download failed. Unable to connect to server")  
            return OFFLINE_RETURN

    # ---------------------------
    #   Loop Processing Methods
    # ---------------------------

    # begin recording loop

    def startloop(self):
        self.recording = True

        self.audiocontrolqueue.put(audioprocessor.Control.ToggleRecording)

        self.led.turn_on()

        return SUCCESS_RETURN

    # stop recording loop, add loop data to composite, and send
    # loop to strangeloop server, if pedal is in online session
    # return:   server response if online, SUCCESS_RETURN if offline

    def endloop(self):

        self.recording = False

        self.led.turn_off()

        time.sleep(END_LOOP_SLEEP)

        self.audiocontrolqueue.put(audioprocessor.Control.ToggleRecording)

        # get loop from audioprocessor object
        # when using vqueues, this will cause a sort of deadlock that prevents the loop from being started again
        if self.virtualize:
            loopdata = np.zeros((int(ARRAY_SIZE_SEC / self.avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE)
        else:
            loopdata = self.audioloopqueue.get()

        # insert loop into offline loops dict
        loopindex = 1
        if len(self.loops):
            loopindex = max(list(self.loops.keys())) + 1
        self.loops[loopindex] = loopdata

        # if pedal in online session, upload json-encoded loop numpy array
        if self.sessionid:

            return self.uploadloop(loopindex)

        return SUCCESS_RETURN

    # remove loop from composite
    # in offline session, only most recent loop is removeable
    # args:     loopindex:  device-unique id for loop to be removed (online only)
    # return:   server response (or SUCCESS_RETURN for offline session)

    def removeloop(self, loopindex=None):
        if loopindex == None and len(self.loops):
            loopindex = max(list(self.loops.keys()))

        if loopindex in self.loops:
            if self.playing and self.playbacklooploopindex == loopindex:
                self.stopplayback()

            if self.sessionid:
                self.slplogger.info("Removing loop %d from session %s" % (loopindex, self.sessionid))

                serverresponse = requests.post(SERVER_URL + "removeloop", data={'mac' : self.mac, 'loopindex' : loopindex}).text
                
                self.slplogger.info("Loop removal returned %s" % serverresponse)

                self.loops.pop(loopindex)

                if serverresponse != SUCCESS_RETURN:
                    updateloops();
                
                return serverresponse

            else:
                self.slplogger.info("Removing loop from offline session...")

                self.loops.pop(loopindex)
                self.genofflinecomposite()            

                return SUCCESS_RETURN
        else:

            self.slplogger.info("Attempted to remove nonexistent loop %d" % loopindex if loopindex is not None else -1)
            return FAILURE_RETURN

    # hear one specific local loop through the pedal instead of the composite
    # can't enter playback mode while recording, can't record while in playback mode
    # args:     loopindex: index of loop to play through pedal
    # return:   SUCCESS_RETURN or FAILURE_RETURN if loop index not present

    def startplayback(self, loopindex):
        if not self.recording and loopindex in self.loops:
            self.playing = True
            self.playbackloopindex = loopindex
            self.audiocompositequeue.put(self.loops[loopindex])
            return SUCCESS_RETURN
        else:
            return FAILURE_RETURN
            
    # stop playing specific local loop and return to playing composite instead
    # return:   SUCCESS_RETURN or FAILURE_RETURN if pedal not in playback mode

    def stopplayback(self):
        if self.playing:
            self.playing = False
            if self.sessionid:
                self.compositepollthread.timestamp = None
            else:
                self.genofflinecomposite()
            return SUCCESS_RETURN
        else:
            return FAILURE_RETURN

    # submit given loop array to server
    # args:     loopindex: index of loop to upload in offline loops dictionary
    # return:   serverresponse or OFFLINE_RETURN on connection failure

    def uploadloop(self, loopindex):
    
        if self.sessionid:

            loopdata = self.loops[loopindex]

            # sort loop array by timestamps before uploading
            loopdata.sort(order="timestamp")

             # write returnaudio numpy array to a virtual bytes file, and then save the bytes output
            loopfile = BytesIO()
            np.save(loopfile, loopdata)

            # seek start of loopfile so that requests module can send it
            loopfile.seek(0)

            try:
                self.slplogger.info("Uploading loop %d to session %s" % (loopindex, self.sessionid))

                serverresponse = requests.post(SERVER_URL + "addloop", data={'mac' : self.mac, 'index' : loopindex}, files={'npdata' : loopfile}).text

                self.slplogger.info("Loop upload %s" % ("successful" if serverresponse == SUCCESS_RETURN else "unsuccessful"))
      
                return serverresponse

            except requests.exceptions.ConnectionError:

                self.slplogger.info("Loop upload failed. Unable to connect to server")  
                return OFFLINE_RETURN

        else:
            return FAILURE_RETURN

    # ------------------
    #   Helper Methods
    # ------------------

    # items that need to be completed when pedal enters online session

    def goonline(self):
        self.getmembers()

        self.updateloops()

        if not self.compositepollstarted:
            self.compositepollstarted = True
            self.compositepollthread.start()

        # pull full composite from server whenever entering online state
        self.compositepollthread.timestamp = None
        self.compositepollthread.stop.clear()

    # items that need to be completed when pedal leaves online session

    def gooffline(self):
        self.sessionid = None
        self.owner = False

        # when offline, only this pedal's loops will be played
        self.genofflinecomposite()

        self.compositepollthread.stop.set()


    # generates composite from offline loops and pushes it to the audio processing composite queue

    def genofflinecomposite(self):
        # sort loops in ascending order of index, so that the first loop serves as the base
        sortedloops = [loop for _, loop in sorted(self.loops.items(), key=lambda item: item[0])]
        composite = combineloops(sortedloops, bytestore=False)
        self.audiocompositequeue.put(composite)

    # downloads and returns a given loop from the server 
    # args:     loopindex: index of loop to download
    # return:   loop data, FAILURE_RETURN if loop index not found, OFFLINE_RETURN on failure to connect

    def getloop(self, loopindex):
        try:
            self.slplogger.info("Downloading loop %d" % loopindex)

            serverresponse = requests.post(SERVER_URL + "getloop", data={'mac' : self.mac, 'index' : loopindex})

            self.slplogger.info("Downloaded loop %d: %s" % (loopindex, str(serverresponse.text[:min(10, len(serverresponse.text))])))

            if serverresponse.text not in [NONE_RETURN, FAILURE_RETURN] and serverresponse.content:
                try:
                    return np.load(BytesIO(serverresponse.content), allow_pickle=False)
                except ValueError:
                    self.slplogger.error("Server returned invalid loop numpy array: %s" % serverresponse[: min(100, len(serverresponse))])
            return FAILURE_RETURN
        except requests.exceptions.ConnectionError:

            self.slplogger.info("Loop download failed. Unable to connect to server")  
            return OFFLINE_RETURN
