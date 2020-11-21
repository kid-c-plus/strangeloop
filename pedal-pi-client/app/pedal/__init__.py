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

END_LOOP_SLEEP = 0.0

# delays to pause between execution of Raspberry Pi and strangeloop server monitoring threads
# by far the most crucial thread is the AudioProcessing one
RPI_POLL_INTERVAL = 0.1
COMPOSITE_POLL_INTERVAL = 2

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
            if self.debug:
                self.played = 0
                self.dropped = 0
            
            self.saveoutput = False
            if self.saveoutput:
                self.audiofile = open("/opt/strangeloop/pedal-pi-client/app/pedal/debug-%s.raw" % datetime.now().timestamp(), mode="w")
            
        # main thread execution loop

        def run(self):
            compositeindex = 0
            compositepassstart = 0
            looprecstart = 0
            while self.pedal.running:
                passtime = time.time()
                self.monitors += 1

                # update average cycle period every 100 cycles
                # this is a pedal property because the loop merging algorithm needs it
                if not self.monitors % 100:
                    self.pedal.avgsampleperiod = (passtime - self.uptime) / self.monitors

                debugpass = self.debug and not (self.monitors - 1) % 50000
                if debugpass:
                    print("average sample period: %f seconds\nsampling frequency: %f Hz" % (self.pedal.avgsampleperiod, 1 / self.pedal.avgsampleperiod))

                if self.pedal.monitoring:

                    # read from AUX input
                    inputbits = self.pedal.audioin.read()
                    outputbits = inputbits

                    if self.pedal.compositedata is not None:

                        # skip all the composite samples that are older than the current time in this composite pass
                        # because of audio sampling slowdown, the composite gets played back slower than it was recorded, causing pitch shifting and a bad sound overall
                        # I'd rather skip samples than have that keep happening
                        
                        while self.pedal.compositedata is not None and compositeindex < self.pedal.compositedata.shape[1] and self.pedal.compositedata[1][compositeindex] < passtime - compositepassstart - (COMP_SAMPLE_WINDOW * self.pedal.avgsampleperiod):
                            if debugpass:
                                print("sample skipped: sample timestamp %f ms, current timestamp %f ms, acceptable window %f ms" % (self.pedal.compositedata[1][compositeindex] * 1000, (passtime - compositepassstart) * 1000, (COMP_SAMPLE_WINDOW * self.pedal.avgsampleperiod)))
                            compositeindex += 1
                            self.dropped += 1
                        
                        # of course, I have to watch out not to go in the other direction, and play this stuff back too fast!
                        # if the next sample is (1 + COMP_SAMPLE_WINDOW) farther ahead than the average sample period, then I'll wait for the next one to hit it
                        # the window is to reduce the chance of waiting to play a sample one time and then missing it the next
                        # I have a similar window guard on old samples

                        if compositeindex < self.pedal.compositedata.shape[1] and self.pedal.compositedata[1][compositeindex] < passtime - compositepassstart + (1 + COMP_SAMPLE_WINDOW * self.pedal.avgsampleperiod):
                            if debugpass:
                                print("playing loop sample!")
                            compositebits = self.pedal.compositedata[0][compositeindex]
                            outputbits = inputbits + compositebits - (inputbits + compositebits) // 2
                            compositeindex += 1
                            self.played += 1
                        elif debugpass:
                            print("sample held for next cycle: sample timestamp %f ms, current timestamp %f ms, acceptable window %f ms, composite index %d" % (self.pedal.compositedata[1][compositeindex] * 1000, (passtime - compositepassstart) * 1000, (COMP_SAMPLE_WINDOW * self.pedal.avgsampleperiod), compositeindex))

                        # return to the start of the composite, and note the time that this playback began
                        if compositeindex >= self.pedal.compositedata.shape[1]:
                            compositeindex = 0
                            compositepassstart = passtime
                    else:
                        compositeindex = 0

                    if self.pedal.recording:
                        if self.pedal.firstrecpass:
                            if self.pedal.debug:
                                print("setting first rec pass timestamp: value %f" % passtime)
                            # we need to keep track of where we started recording relative to the composite, so that we can normalize them again once the loop's done
                            self.pedal.loopoffset = compositeindex
                            # time when this loop began
                            looprecstart = passtime
                            self.pedal.firstrecpass = False

                        # loop length is unbounded. add 10 seconds to loop np array
                        if self.pedal.loopiter >= self.pedal.loopdata.shape[1]:
                            self.pedal.loopdata = np.append(self.pedal.loopdata, np.zeros((2, int(ARRAY_SIZE_SEC / self.pedal.avgsampleperiod)), dtype=float), axis=1)

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
                print("played loop samples: %f percent" % (self.played * 100 / (self.played + self.dropped)))
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
        try:
            self.getsession(timeout=1)
            if self.sessionid:
                self.getmembers()
            self.online = True
        except requests.exceptions.ConnectionError:
            self.online = False

        # initialize with empty composite array
        self.compositedata = None
        self.lastcomposite = None

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
    # return:   newly created session identifier on success, or server response on failure

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

    # end session
    # updates pedal object sessionid & owner variables
    # return:   server response

    def endsession(self):
        serverresponse = requests.post(SERVER_URL + "endsession", data={'mac' : self.mac}).text
        if serverresponse == SUCCESS_RETURN:
            self.sessionid = None
            self.owner = False
            self.compositepollthread.stop.set()
        else:
            self.getsession()
        return serverresponse

    # join session
    # updates pedal object sessionid & owner variables
    # args:     nickname:   self-appointed identifier to the other users in the session (need not be unique)
    # return:   server response

    def joinsession(self, nickname, sessionid):
        serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text
        if serverresponse == FAILURE_RETURN:
            self.getsession()
        elif serverresponse == SUCCESS_RETURN:
            self.sessionid = sessionid
            self.owner = False
            self.compositepollthread.start()
        return serverresponse

    # leave session (without ending it)
    # updates pedal object sessionid & owner variables
    # return:   server response
    
    def leavesession(self):
        serverresponse = requests.post(SERVER_URL + "leavesession", data={'mac' : self.mac}).text
        if serverresponse == SUCCESS_RETURN:
            self.sessionid = None
            self.owner = False
            self.compositepollthread.stop.set()
        return serverresponse

    # update pedal object sessionid & owner variables (without actually returning them)
    # args:     **kwargs to pass to request GET call
    # return:   server response
    
    def getsession(self, **kwargs):
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

    # updat pedal object sessionmembers list
    # return:       server response

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

    # ---------------------------
    #   Loop Processing Methods
    # ---------------------------

    # begin recording loop

    def startloop(self):
        self.recording = True
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

        # synchronize loop to existing composite
        if self.compositedata is not None:

            print("adding loop to composite")
            # roll array along...x-axis (?) to synchronize it with the composite
            self.loopdata = np.roll(self.loopdata, self.loopoffset, axis=1)

            # update timestamps accordingly
            # before rolling, timestamp array was [0..timestampmax]
            # now, it's [timestamp[loopoffset]..timestampmax, 0..timestamp[loopoffset - 1]]
            # each timestamp needs to be reduced by timestamp[loopoffset] and then modulated by
            # (timestampmax + avgsampleperiod), or else the max timestamp would also be zero
            timestampdiff = self.loopdata[1][0]
            timestampmod = max(self.loopdata[1]) + self.avgsampleperiod
            self.loopdata[1] = (self.loopdata[1] - timestampdiff) % timestampmod
            
            # save the last composite to enable offline loop deletion (only of the most recent loop)
            self.lastcomposite = self.compositedata
            self.compositedata = mergeloops(self.loopdata, self.compositedata)
            
        else:
            self.compositedata = self.loopdata

        # if pedal in online session, upload json-encoded loop numpy array
        if self.sessionid:
            
            # provide device-unique loop index
            loopindex = self.loopindex
            self.loops.append(loopindex)
            self.loopindex += 1
            serverresponse = requests.post(SERVER_URL + "addtrack", data={'mac' : self.mac, 'index' : loopindex}, files={'wavdata' : StringIO(json.dumps(loopdata.tolist()))}).text

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
            return SUCCESS_RETURN
