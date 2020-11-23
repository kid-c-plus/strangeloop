from app import db
import sqlalchemy
import numpy as np

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
    tracks = db.relationship("Track", backref="session", lazy=False)

    # combines tracks into composite loop numpy array
    # args:     fromscratch: indicates whether to recombine all tracks or just add tracks added since last modified (generally, the former is used when deleting tracks and the latter when adding)
    def generatecomposite(self, fromscratch):
        if len(self.tracks):
            if self.composite and not fromscratch:
                self.composite = Session.combinetracks([track for track in self.tracks if track.timestamp > self.lastmodified], composite=self.composite)
            else:
                self.composite = Session.combinetracks(self.tracks)
            self.lastmodified = max([track.timestamp for track in self.tracks])
        else:
            self.composite = None
            self.lastmodified = None

    # actually combines given wav data array using same timestamp-maintaining algorithm as the pedal
    # return:   byte representation of composite array given by numpy.save()
    def combinetracks(tracks, composite=None):
        if len(tracks):
            compositeaudio = None
            if composite:
                compositeaudio = np.load(BytesIO(composite))
            for track in tracks:
                trackaudio = np.load(BytesIO(trackaudio.npdata))
                compositeaudio = mergeloops(compositeaudio, trackaudio)
            
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

    tracks = db.relationship("Track", backref="pedal", lazy=False)

    def __repr__(self):
        return "<Pedal %s>" % self.mac

class Track(db.Model):
    pedalmac = db.Column(db.String(18), db.ForeignKey("pedal.mac"), primary_key=True)
    index = db.Column(db.String(4), primary_key=True)
    timestamp = db.Column(db.DateTime)
    npdata = db.Column(db.LargeBinary, nullable=False)

    sessionid = db.Column(db.String(4), db.ForeignKey("session.id"))

    def __repr__(self):
        return "<Track %s:%s>" % (self.pedalmac, self.index)
