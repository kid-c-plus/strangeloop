from app import flaskapp, pedal
import flask

# -------------
#   Constants
# -------------

STATIC_DIR = "/opt/strangeloop/pedal-pi-client/app/static"

# --------------------------------
#   Client-Server Endpoints
# --------------------------------

@flaskapp.route("/")
def index():
    return flask.render_template("index.html", pedal=pedal)
 
# ------------------------------
#   Synchronous POST endpoints
# ------------------------------

@flaskapp.route("/newsession", methods=["POST"])
def newsession():
    nickname = flask.request.values['nickname']
    if nickname:
        nickname = str(nickname)
        pedalresponse = pedal.newsession(nickname)
        if pedalresponse == pedal.SUCCESS_RETURN:
            flask.flash("Created session %s" % pedal.sessionid)
        else:
            flask.flash({
                pedal.NONE_RETURN       : "Pedal already in session %s. Session not created." % pedal.sessionid,
                pedal.FAILURE_RETURN    : "Server error. Session not created.",
                pedal.FULL_RETURN       : "Server full. Session not created."
                }[pedalresponse])
    else:
        flask.flash("Nickname required.")
    return flask.redirect(flask.url_for("/index"))

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    sessionid = flask.request.values['sessionid']
    nickname = flask.request.values['nickname']
    if sessionid and nickname:
        sessionid = str(sessionid)
        nickname = str(nickname)
        pedalresponse = pedal.joinsession(nickname, sessionid)
        if pedalresponse == pedal.SUCCESS_RETURN:
            flask.flash("Joined session %s." % pedal.sessionid)
        else:
            flask.flash({
                pedal.FAILURE_RETURN    : "Pedal already in session %s. Session %s not joined." % (pedal.sessionid, sessionid) if pedal.sessionid else "Session %s not found." % sessionid,
                pedal.FULL_RETURN       : "Session %s is full." % sessionid
            }[pedalresponse])
    else:
        flask.flash("Session ID and nickname required.")
    return flask.redirect(flask.url_for("/index"))

@flaskapp.route("/endsession", methods=["POST"])
def endsession():
    pedalresponse = pedal.endsession()
    if pedalresponse == pedal.SUCCESS_RETURN:
        flask.flash("Session ended.")
    else:
        flask.flash("Session %s is not owned by you." % pedal.sessionid if pedal.sessionid else "Pedal not in session.")
    return flask.redirect(flask.url_for("/index"))

@flaskapp.route("/leavesession", methods=["POST"])
def leavesession():
    pedalresponse = pedal.leavesession()
    if pedalresponse == pedal.SUCCESS_RETURN:
        flask.flash("Session ended.")
    else:
        flask.flash("Pedal not in session.")
    return flask.redirect(flask.url_for("/index"))

# -------------------------------
#   Asynchronous POST endpoints
# -------------------------------

@flaskapp.route("/toggleloop", methods=["POST"])
def toggleloop():
    if pedal.recording:
        pedal.endloop()
        return "Loop recorded."
    else:
        pedal.startloop()
        return "Recording loop..."
# ------------------------------
#   Asynchronous GET endpoints
# ------------------------------

# check current session membership
@flaskapp.route("/getsession")
def getsession():
    pedalresponse = pedal.getsession()
    if pedalresponse == pedal.SUCCESS_RETURN:
        return "%s %s %s" % (pedal.SUCCESS_RETURN, pedal.sessionid, "owner" if self.owner else "member")
    else:
        return pedalresponse


# -------------------------------
#   Static Fileserver Endpoints
# -------------------------------

for file in STATIC_FILES:
    flaskapp.add_url_rule
