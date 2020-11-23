from app import db
import sqlalchemy
import numpy as np

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
    duration = db.Column(db.Float, nullable=True)
    composite = db.Column(db.LargeBinary, nullable=True)

    pedals = db.relationship("Pedal", backref="session", lazy=False)
    tracks = db.relationship("Track", backref="session", lazy=False)

    # combines tracks into composite loop numpy array
    # args:     fromscratch: indicates whether to recombine all tracks or just add tracks added since last modified (generally, the former is used when deleting tracks and the latter when adding)
    def generatecomposite(self, fromscratch):
        if len(self.tracks):
            if self.composite and not fromscratch:
                self.composite, _ = Session.combinetracks([track for track in self.tracks if track.timestamp > self.lastmodified], composite=self.composite)
            else:
                self.composite, self.duration = Session.combinetracks(self.tracks)
            self.lastmodified = max([track.timestamp for track in self.tracks])
        else:
            self.composite = None
            self.duration = None
            self.lastmodified = None

    # actually combines given wav data array using same timestamp-maintaining algorithm as the pedal
    def combinetracks(tracks, composite=None):

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

        if len(tracks):
            if composite:
                returnaudio = np.load(BytesIO(composite))
            else:
                returnaudio = None
            for track in tracks:
                trackaudio = np.load(BytesIO(trackaudio.wavdata))
                
            return (returnaudio, len(returnaudio))
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
    wavdata = db.Column(db.LargeBinary, nullable=False)

    sessionid = db.Column(db.String(4), db.ForeignKey("session.id"))

    def __repr__(self):
        return "<Track %s:%s>" % (self.pedalmac, self.index)
