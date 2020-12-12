import numpy as np
from enum import Enum
import time

from . import rpi

AUDIO_OUT       = {
    'PWM0'  : 18,
    'PWM1'  : 13
}

# loops can be up to 2 minutes long
MAX_LOOP_DURATION = 120

# numpy dtype to define loop & composite array entries
LOOP_ARRAY_DTYPE = [('value', int), ('timestamp', float)]

# add 10 seconds worth of loop time to the array each time its length is met
ARRAY_SIZE_SEC = 10

# enum to map control commands passed from main thread to program state dict keys
class Control(str, Enum):
    EndProcess          = "running"
    ToggleMonitoring    = "monitoring"
    ToggleRecording     = "recording"
    RemoveLoop          = "removeloop"

# ----------------------------------------------------------------------------------------------------
#   run:    process tasked with processing and recording audio input
#   args:   controlqueue:       FIFO inbound queue containing pedal state change information
#           compositequeue:     FIFO inbound queue containing downloaded composite numpy arrays
#           loopqueue:          FIFO outbound queue used by AudioProcessor to export recorded loops
#           logqueue:           FIFO outbound queue to pass logs to parent Pedal process
#           kwargs:             Dictionary containing AudioProcessor settings passed to Pedal object
# ----------------------------------------------------------------------------------------------------

def run(controlqueue, compositequeue, loopqueue, logqueue, kwargs):

    logqueue.put(("INFO", "AudioProcessor - Starting execution..."))

    # simple helper method to append whitespace to array
    # return: new array with whitespace appended
    def extendarray(arr, avgsampleperiod=(1 / 44100.0)):
        return np.append(arr, np.zeros((int(ARRAY_SIZE_SEC / avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE)) if arr is not None else np.zeros((int(ARRAY_SIZE_SEC / avgsampleperiod)), dtype=LOOP_ARRAY_DTYPE) 

    # simple helper to read a single number out of a file of space-separated numbers
    def readitem(fileobj):
        retitem = ""
        while True:
            char = fileobj.read(1)
            if not char or char == "" or char == " ":
                break
            retitem += char
        return retitem


    # gets all queued commands and applies them to status dict
    def updatestatus(status, queue):
        while not queue.empty():
            statuschange = queue.get()
            status[statuschange.value] = not status[statuschange.value]

    audioin        = rpi.SPI()
    audioout       = rpi.PWM((AUDIO_OUT['PWM0'], AUDIO_OUT['PWM1']))

    status = {
        'running'       : True,
        'monitoring'    : False,
        'recording'     : False,
        'removeloop'    : False
    }

    # initialize values for composite iteration & timestamp calculation
    # compositepassstart: timestamp when the composite loop was last started or restarted
    # looprecstart: timestamp of the beginning of loop recording
    #               (only used when composite is empty. otherwise, all loop timestamp data
    #               is stored relative to the compositepassstart timestamp)
    # monitors: used for diagnostics & calculating avgsampleperiod
    compositeindex = lastcompositeindex = compositepassstart = compositenorm = loopindex = looprecstart = monitors = passtime = 0

    avgsampleperiod = (1 / 44100.0)
    uptime = time.time()

    compositedata       = extendarray(None)
    lastcompositedata   = extendarray(None)
    loopdata            = extendarray(None)

    emptycomposite = emptylastcomposite = True

    audioinfileobj = None    
    if kwargs.get('audioloadinput', False) and kwargs.get('audioinfile', False):
        audioinfileobj = open(kwargs['audioinfile'])

    audiooutfileobj = None    
    if kwargs.get('audiosaveoutput', False) and kwargs.get('audiooutfile', False):
        audiooutfileobj = open(kwargs['audiooutfile'], mode="w")
    
    updatestatus(status, controlqueue)

    while status['running']:

        # IPC tasks

        # pull new composite
        while not compositequeue.empty():
            compositedata = compositequeue.get()

            # composite is returning to empty state
            if compositedata is None:
                compositedata = extendarray(None)
                emptycomposite = True
                looprecstart = 0
            else:
                emptycomposite = False
            
            # recalculate compositenorm
            compositenorm = np.mean(compositedata[:]['value'], dtype=int)

        # a new loop has been recorded, submit it to the output queue
        if loopindex and not status['recording']:
            logqueue.put(("INFO", "AudioProcessor - Ending loop..."))

            loopqueue.put(loopdata[:loopindex])
    
            if emptycomposite:
                compositedata = compositedata[:loopindex]
                emptycomposite = False

            # recalculate compositenorm
            compositenorm = np.mean(compositedata[:]['value'], dtype=int)

            loopindex = 0
            loopdata = np.zeros_like(compositedata)

        elif not loopindex and status['recording']:
            logqueue.put(("INFO", "AudioProcessor - Starting loop..."))
    
            lastcompositedata = np.copy(compositedata)
            emptylastcomposite = emptycomposite

        # it's kind of an outlier in the Control enum but this is the easiest way to delete a loop offline
        if status['removeloop'] and not status['recording']:
            logqueue.put(("INFO", "AudioProcessor - Removing loop..."))

            compositedata = lastcompositedata
            emptycomposite = emptylastcomposite
            status['removeloop'] = False

        # need deterministic timestamps for unit testing
        if audioinfileobj:
            passtime += 1

        else:
            # current timestamp
            passtime = time.time()

        # used for diagnostics (specifically calculating sampling frequency)
        monitors += 1

        # update average cycle period every 100 cycles
        if not monitors % 100:
            avgsampleperiod = (passtime - uptime) / monitors

        # determines whether some debug information is printed
        debugpass = not (monitors - 1) % 100000

        if status['monitoring']:

            # read from input file (for unit testing)
            if audioinfileobj:
                inputcommand = readitem(audioinfileobj)
                if inputcommand.isdigit():
                    inputbits = int(inputcommand)
                else: 
                    # eof
                    if not inputcommand:
                        status['running'] = False
                    elif inputcommand in status:
                        status[inputcommand] = not status[inputcommand]
                    continue

            # read from AUX input
            else:
                inputbits = audioin.read()

            outputbits = inputbits

            # no composite loop data to play
            if emptycomposite:

                # reset composite-related variables
                if compositeindex or lastcompositeindex or compositepassstart:
                    compositeindex = lastcompositeindex = compositepassstart = 0

                if status['recording']:

                    # if looprecstart is zero, this is the first recording pass
                    if not looprecstart:
                        looprecstart = passtime

                    looprectimestamp = passtime - looprecstart

                    # don't record past maximum loop length
                    if looprectimestamp < MAX_LOOP_DURATION:

                        # loop length is unbounded. add 10 seconds to loop np array
                        if loopindex >= len(loopdata):
                            loopdata = extendarray(loopdata, avgsampleperiod)

                        # composite is also unbound on first loop
                        if loopindex >= len(compositedata):
                            compositedata = extendarray(compositedata)

                        # save input to both composite and loopdata array to upload to server
                        # store timestamp relative to composite playback head, and sort array by timestamps before submitting
                        loopdata[loopindex] = compositedata[loopindex] = (inputbits, looprectimestamp)
                        loopindex += 1

                else:

                    # reset first loop record variable
                    if looprecstart:
                        looprecstart = 0

            else:

                # compositepassstart of zero indicates this is the first pass where composite will be played 
                # if playback & recording have reached the end of the composite, return to the start, and note the time new playback began
                if not compositepassstart or compositeindex >= len(compositedata) - 1:
                    compositeindex = 0
                    compositepassstart = passtime

                # playback timestamp relative to the start of the composite
                inputtimestamp = passtime - compositepassstart

                # search in the composite for the closest timestamps higher and lower than the current timestamp (relative to composite start time)
                # could use binary search, but in practice this should be within a small number of array indices away from the current composite index
                # each time, as long as sampling rate stays constant. so, though the worst-case big-o of this is worse, it'll perform better on average

                lastcompositeindex = compositeindex

                while compositeindex < len(compositedata) - 1 and inputtimestamp > compositedata[compositeindex + 1]['timestamp']:
                    compositeindex += 1 

                # play & write to the closer of the two samples adjoining the current timestamp (or the index sample if the index is at the end of the array)
                compositeindex = compositeindex if (compositeindex == len(compositedata) - 1 or inputtimestamp - compositedata[compositeindex]['timestamp'] <= compositedata[compositeindex + 1]['timestamp'] - inputtimestamp) else compositeindex + 1

                compositebits = compositedata[compositeindex]['value']

                # merge input and output bits by adding them and subtracting the mean of the composite array
                outputbits = inputbits + compositebits - compositenorm

                if status['recording']:

                    # add merged input and composite
                    # write to all indices between the last written one and this one
                    # which will result in some pretty square sonic waves, but it's better than having composite array
                    # indices that aren't written to by subsequent loops
                    if lastcompositeindex <= compositeindex:
                        compositedata[lastcompositeindex + 1 : compositeindex + 1]['value'] +=  inputbits - compositenorm

                    # if the composite index looped around since last pass
                    # even if the compositedata array has changed size since the last pass, and lastcompositeindex is larger
                    # than the end of the array, this won't throw an error, it'll just only write the [ : compositeindex + 1] piece
                    else:
                        compositedata[lastcompositeindex + 1 : ]['value'] += inputbits - compositenorm
                        compositedata[ : compositeindex + 1]['value'] += inputbits - compositenorm

                    # loop length is unbounded. add 10 seconds to loop np array
                    if loopindex >= len(loopdata):
                        loopdata = extendarray(loopdata, avgsampleperiod)

                    # save input to loopdata array to upload to server
                    # store timestamp relative to composite playback head, and sort array by timestamps before submitting
                    loopdata[loopindex] = (inputbits, inputtimestamp)
                    loopindex += 1

            # write to AUX output
            if kwargs.get('audioplayoutput', True):
                audioout.write(outputbits)

            # save to output file
            if audiooutfileobj:
                try:
                    audiooutfileobj.write("%d " % outputbits)
                except:
                    pass

        # get status for next pass
        updatestatus(status, controlqueue)

    # Deinitialization actions
    logqueue.put(("INFO", "Monitoring frequency: %f" % (monitors / (time.time() - uptime))))
    if audioinfileobj:
        audioinfileobj.close()
    if audiooutfileobj:
        audiooutfileobj.close()

