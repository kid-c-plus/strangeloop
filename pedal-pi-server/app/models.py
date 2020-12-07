from app import db
import sqlalchemy
import numpy as np
from io import BytesIO

from common import *

# -------------
#   Constants
# -------------

SAMPLE_MAC = "12:34:56:ab:cd:ef"

# loops can be up to 2 minutes long
MAX_LOOP_DURATION = 120

# numpy dtype to define loop & composite array entries
LOOP_ARRAY_DTYPE = [('value', int), ('timestamp', float)]

# -----------
#	Methods
# -----------

# helper method to add a loop to the composite
# args:     composite: composite loop
#           loop: new loop to add
def mergeloops(composite, loop):
	if composite is None:
		return loop

	composite = [entry for entry in composite if entry['timestamp'] < MAX_LOOP_DURATION]

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

		compositebits = composite[compositeindex]['value']

		# merge input and output bits by adding them and subtracting the mean of the composite array
		outputbits = inputbits + compositebits - compositenorm

		# add merged input and composite, and average timestamps of composite recording and current input
		# write to all indices between the last written one and this one
		# which will result in some pretty square sonic waves, but it's better than having composite array
		# indices that aren't written to by subsequent loops
		if lastcompositeindex <= compositeindex:
			composite[lastcompositeindex + 1 : compositeindex + 1] = (outputbits, (inputtimestamp + composite[compositeindex]['timestamp']) / 2)

		# if the composite index looped around since last pass
		# even if the composite array has changed size since the last pass, and lastcompositeindex is larger
		# than the end of the array, this won't throw an error, it'll just only write the [ : compositeindex + 1] piece
		else:
			composite[lastcompositeindex + 1 : ] = composite[ : compositeindex + 1] = (outputbits, (inputtimestamp + composite[compositeindex]['timestamp']) / 2)

		lastcompositeindex = compositeindex

		# save input to loop array to upload to server
		# store timestamp relative to composite playback head, and sort array by timestamps before submitting
		loop[loopindex] = (inputbits, inputtimestamp)
		loopindex += 1 

	return composite

# -------------------
#   Database Models
# -------------------

class Session(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    timestamp = db.Column(db.DateTime)
    ownermac = db.Column(db.String, nullable=False)
    lastmodified = db.Column(db.DateTime, nullable=True)
    composite = db.Column(db.LargeBinary, nullable=True)

    pedals = db.relationship("Pedal", backref="session", lazy=False)
    loops = db.relationship("Loop", backref="session", lazy=False)

    # combines loops into composite loop numpy array
    # args:     fromscratch: indicates whether to recombine all loops or just add loops added since last modified (generally, the former is used when deleting loops and the latter when adding)
    def generatecomposite(self, fromscratch):
        if len(self.loops):
            if self.composite and not fromscratch:
                self.composite = Session.combineloops([loop for loop in self.loops if loop.timestamp > self.lastmodified], composite=self.composite)
            else:
                self.composite = Session.combineloops(self.loops)
            self.lastmodified = max([loop.timestamp for loop in self.loops])
        else:
            self.composite = None
            self.lastmodified = None

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

    def __repr__(self):
        return "<Session %s>" % self.id

class Pedal(db.Model):
    # 18 characters for the MAC address
    mac = db.Column(db.String(18), primary_key=True)
    nickname = db.Column(db.String(32), nullable=False)

    sessionid = db.Column(db.String(8), db.ForeignKey("session.id"), nullable=True)

    loops = db.relationship("Loop", backref="pedal", lazy=False)

    def __repr__(self):
        return "<Pedal %s>" % self.mac

class Loop(db.Model):
    pedalmac = db.Column(db.String(18), db.ForeignKey("pedal.mac"), primary_key=True)
    index = db.Column(db.String(4), primary_key=True)
    timestamp = db.Column(db.DateTime)
    npdata = db.Column(db.LargeBinary, nullable=False)

    sessionid = db.Column(db.String(4), db.ForeignKey("session.id"))

    def __repr__(self):
        return "<Loop %s:%s>" % (self.pedalmac, self.index)
