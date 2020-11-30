from app import db
import sqlalchemy
import numpy as np
from io import BytesIO

from common import *

# -------------
#   Constants
# -------------

SAMPLE_MAC = "12:34:56:ab:cd:ef"

MAX_TRACK_DURATION = 60000

PYDUB_ARGS = {
    'sample_width'  : 2,
    'frame_rate'    : 44100,
    'channels'      : 2
    }

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
                compositeaudio = np.load(BytesIO(composite))
            for loop in loops:
                loopaudio = np.load(BytesIO(loop.npdata))
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
