# common.py - file containing functionality common to client and server
import numpy as np
from io import BytesIO

# -------------
#   Constants
# -------------

# string responses sent by server
SUCCESS_RETURN = "True"
FAILURE_RETURN = "False"
FULL_RETURN = "Full"
NONE_RETURN = "None"
EMPTY_RETURN = "Empty"
COLLISION_RETURN = "Collision"
# return value if unable to connect to server
OFFLINE_RETURN = "Offline"

# loops can be up to 2 minutes long
MAX_LOOP_DURATION = 120

# -----------
#   Methods
# -----------

# helper method to add a loop to the composite
# args:     composite: composite loop
#           loop: new loop to add
def mergeloops(composite, loop):
    if composite is None:
        return loop

    composite = composite[composite['timestamp'] < MAX_LOOP_DURATION]

    if loop is None:
        return composite

    compositeindex = lastcompositeindex = loopindex = 0
    compositenorm = np.mean(composite[:]['value'], dtype=int)
    
    # add all of loop to composite, looping through composite multiple times if necessary
    while loopindex < len(loop):

        if compositeindex >= len(composite):
            compositeindex = 0
    
        inputvalue, inputtimestamp = loop[loopindex]

        while compositeindex < len(composite) - 1 and inputtimestamp > composite[compositeindex + 1]['timestamp']:
            compositeindex += 1

        # play & write to the closer of the two samples adjoining the current timestamp (or the index sample if the index is at the end of the array)
        compositeindex = compositeindex if (compositeindex == len(composite) - 1 or inputtimestamp - composite[compositeindex]['timestamp'] <= composite[compositeindex + 1]['timestamp'] - inputtimestamp) else compositeindex + 1

        compositevalue = composite[compositeindex]['value']

        # merge input and output value by adding them and subtracting the mean of the composite array
        outputvalue = inputvalue + compositevalue - compositenorm

        # add merged input and composite, and average timestamps of composite recording and current input
        # write to all indices between the last written one and this one
        # which will result in some pretty square sonic waves, but it's better than having composite array
        # indices that aren't written to by subsequent loops
        if lastcompositeindex <= compositeindex:
            composite[lastcompositeindex + 1 : compositeindex + 1]['value'] +=  inputvalue - compositenorm


        # if the composite index looped around since last pass
        # even if the composite array has changed size since the last pass, and lastcompositeindex is larger
        # than the end of the array, this won't throw an error, it'll just only write the [ : compositeindex + 1] piece
        else:
            composite[lastcompositeindex + 1 : ] = composite[ : compositeindex + 1] = (outputvalue, (inputtimestamp + composite[compositeindex]['timestamp']) / 2)
            compositedata[lastcompositeindex + 1 : ]['value'] += inputvalue - compositenorm
            compositedata[ : compositeindex + 1]['value'] += inputvalue - compositenorm

        lastcompositeindex = compositeindex

        # save input to loop array to upload to server
        # store timestamp relative to composite playback head, and sort array by timestamps before submitting
        loop[loopindex] = (inputvalue, inputtimestamp)
        loopindex += 1 

    return composite

# actually combines given numpy data arrays using same timestamp-maintaining algorithm as the pedal
# return:   byte representation of composite array given by numpy.save()
def combineloops(loops, composite=None):
    if len(loops):
        compositeaudio = None
        if composite:
            compositeaudio = np.load(BytesIO(composite), allow_pickle=False)
        for loop in loops:
            loopaudio = np.load(BytesIO(loop.npdata), allow_pickle=False)
            compositeaudio = mergeloops(compositeaudio, loopaudio)
        
        # write returnaudio numpy array to a virtual bytes file, and then save the bytes output
        returnfile = BytesIO()
        np.save(returnfile, compositeaudio)
        returndata = returnfile.getvalue()
            
        return returndata
    else:
        return None


