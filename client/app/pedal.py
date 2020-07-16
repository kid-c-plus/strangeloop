import uuid
import requests
import time
import atexit
from threading import Thread, Event, main_thread
from datetime import datetime
from pydub import AudioSegment
from io import BytesIO

# -------------
#   Constants
# -------------

SERVER_URL = "http://localhost:5000/"

SUCCESS_RETURN = "True"
FAILURE_RETURN = "False"
FULL_RETURN = "Full"
NONE_RETURN = "None"

END_LOOP_SLEEP = 0.1
COMPOSITE_POLL_INTERVAL = 2

AUDIO_CHUNK = 256 
PYAUDIO_ARGS = {
    'format'            : pyaudio.paInt16,
    'channels'          : 2,
    'rate'              : 44100,
    'frames_per_buffer' : AUDIO_CHUNK
}

PYDUB_ARGS = {
    'sample_width'  : 2,
    }


# class handling all the basic functionality of a looper pedal. the Flask UI receives and interacts with an instance of this class
class Pedal():
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

    class AudioProcessingThread(Thread):
        def __init__(self, pedal, daemon=True):
            Thread.__init__(self, daemon=daemon)
            self.pedal = pedal
            
        def run(self):
            import pyaudio
            audio = pyaudio.PyAudio()
            audioin = audio.open(input=True, start=True, **PYAUDIO_ARGS)
            monitorout = audio.open(output=True, **PYAUDIO_ARGS)
            compositeout = audio.open(output=True, **PYAUDIO_ARGS)
            while self.pedal.monitoring:
                compositeindex = 0
                inputchunk = audioin.read(AUDIO_CHUNK, exception_on_overflow=False)
                while inputchunk != b"":
                    monitorout.write(inputchunk)
                    if self.pedal.compositedata:
                        compositechunk = self.pedal.compositedata[compositeindex : min(compositeindex + len(inputchunk), len(self.pedal.compositedata))]
                        while len(compositechunk) < len(inputchunk):
                            compositechunk += self.pedal.compositedata[: min(len(inputchunk) - len(compositechunk), len(self.pedal.compositedata))]
                        compositeout.write(compositechunk)
                        compositeindex = (compositeindex + len(inputchunk)) % len(self.pedal.compositedata)
                    if self.pedal.recording and (not self.pedal.compositedata or len(self.pedal.loopdata) < len(self.pedal.compositedata)):
                        if not self.pedal.compositedata:
                            self.pedal.loopdata += inputchunk
                        elif len(self.pedal.loopdata) < len(self.pedal.compositedata):
                            self.pedal.loopdata += inputchunk[:min(len(inputchunk), len(self.pedal.compositedata) - len(self.pedal.loopdata))]
                        if self.pedal.firstrec:
                            self.pedal.loopoffset = compositeindex
                            self.pedal.firstrec = False
                    inputchunk = audioin.read(AUDIO_CHUNK, exception_on_overflow=False)

    def __init__(self, debug=False):
        uuidnode = uuid.getnode()
        self.mac = ':'.join(("%012X" % uuidnode)[i:i+2] for i in range(0, 12, 2))
        self.sessionid = None
        self.owner = False
        self.sessionmembers = None

        # check initial session membership
        self.getsession()
        if self.sessionid:
            self.getmembers()

        self.compositedata = None
        self.lastcomposite = None
        self.compositepollthread = Pedal.CompositePollingThread(pedal=self)
        self.processaudiothread = Pedal.AudioProcessingThread(pedal=self, daemon=True)

        self.loopdata = b""
        self.loopoffset = 0
        self.monitoring = True
        self.recording = False

        self.loops = []
        self.loopindex = 1

        self.debug = debug
        if debug:
            self.processaudiothread.start()
            print(self.newsession("rick"))

    def __del__(self):
        self.compositepollthread.stop.set()

        self.audioin.stop_stream()
        self.audioin.close()

        self.monitorout.stop_stream()
        self.monitorout.close()

        self.compositeout.stop_stream()
        self.compositeout.close()
        
        self.monitoring = False

    def newsession(self, nickname):
        serverresponse = requests.post(SERVER_URL + "newsession", data={'mac' : self.mac, 'nickname' : nickname}).text
        if serverresponse != NONE_RETURN and serverresponse != FULL_RETURN:
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
        return serverresponse

    def joinsession(self, nickname, sessionid):
        serverresponse = requests.post(SERVER_URL + "joinsession", data={'mac' : self.mac, 'nickname' : nickname, 'sessionid' : sessionid}).text
        if serverresponse == SUCCESS_RETURN:
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

    def getsession(self):
        serverresponse = requests.post(SERVER_URL + "getsession", data={'mac' : self.mac}).text
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
        self.firstrec = True

    def endloop(self):
        self.recording = False
        time.sleep(END_LOOP_SLEEP)
        # synchronize loop to existing composite
        if self.compositedata:
            if len(self.loopdata) < len(self.compositedata):
                self.loopdata = (self.loopdata + b"\x00" * len(self.compositedata))[:len(self.compositedata)]
            self.loopdata = self.loopdata[self.loopoffset:] + self.loopdata[:self.loopoffset]
        if self.compositedata:
            self.lastcomposite = self.compositedata
            self.compositedata = AudioSegment(data=self.compositedata, **PYDUB_ARGS).overlay(AudioSegment(data=self.loop, **PYDUB_ARGS)).raw_data
        else:
            self.compositedata = self.loopdata
        if self.sessionid:
            loopindex = self.loopindex
            self.loops.append(loopindex)
            self.loopindex += 1
            serverresponse = requests.post(SERVER_URL + "addtrack", data={'mac' : self.mac, 'index' : loopindex}, files={'wavdata' : BytesIO(self.loopdata)}).text
            self.loopdata = b""
            self.getcomposite()
            return serverresponse
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
