/rom app import db
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
                self.composite = combineloops([loop for loop in self.loops if loop.timestamp > self.lastmodified], composite=self.composite)
            else:
                self.composite = combineloops(self.loops)
            self.lastmodified = max([loop.timestamp for loop in self.loops])
        else:
            self.composite = None
            self.lastmodified = None

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
