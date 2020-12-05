from app import flaskapp, pedal
import flask
import os

import sys
sys.path.append("opt/strangeloop/common")
from common import *

# -------------
#   Constants
# -------------

# directory containing static web GUI resource files
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
        if pedalresponse == SUCCESS_RETURN:
            flask.flash("Created session %s" % pedal.sessionid)
        else:
            flask.flash({
                NONE_RETURN       : "Pedal already in session %s. Session not created." % pedal.sessionid,
                FAILURE_RETURN    : "Server error. Session not created.",
                FULL_RETURN       : "Server full. Session not created.",
                OFFLINE_RETURN    : "Unable to communicate with server. Session not created." 
                }[pedalresponse])
    else:
        flask.flash("Nickname required.")
    return flask.redirect(flask.url_for("index"))

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    sessionid = flask.request.values['sessionid']
    nickname = flask.request.values['nickname']
    if sessionid and nickname:
        sessionid = str(sessionid)
        nickname = str(nickname)
        pedalresponse = pedal.joinsession(nickname, sessionid)
        if pedalresponse == SUCCESS_RETURN:
            flask.flash("Joined session %s." % pedal.sessionid)
        else:
            flask.flash({
                FAILURE_RETURN    : "Pedal already in session %s. Session %s not joined." % (pedal.sessionid, sessionid) if pedal.sessionid else "Session %s not found." % sessionid,
                FULL_RETURN       : "Session %s is full." % sessionid,
                OFFLINE_RETURN    : "Unable to communicate with server. Session not joined." 
            }[pedalresponse])
    else:
        flask.flash("Session ID and nickname required.")
    return flask.redirect(flask.url_for("index"))

@flaskapp.route("/endsession", methods=["POST"])
def endsession():
    pedalresponse = pedal.endsession()
    if pedalresponse == SUCCESS_RETURN:
        flask.flash("Session ended.")
    elif pedalresponse == OFFLINE_RETURN:
        flask.flash("Unable to communicate with server. Session not ended.")
    else:
        flask.flash("Session %s is not owned by you." % pedal.sessionid if pedal.sessionid else "Pedal not in session.")
    return flask.redirect(flask.url_for("index"))

@flaskapp.route("/leavesession", methods=["POST"])
def leavesession():
    pedalresponse = pedal.leavesession()
    if pedalresponse == SUCCESS_RETURN:
        flask.flash("Session ended.")
    elif pedalresponse == OFFLINE_RETURN:
        flask.flash("Unable to communicate with server. Session not left.")
    else:
        flask.flash("Pedal not in session.")
    return flask.redirect(flask.url_for("index"))

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
    if pedalresponse == SUCCESS_RETURN:
        return "%s %s %s" % (SUCCESS_RETURN, pedal.sessionid, "owner" if pedal.owner else "member")
    elif pedalresponse == OFFLINE_RETURN:
        flask.flash("Unable to communicate with server. Session not ended.")
    return pedalresponse


# -------------------------------
#   Static Fileserver Endpoints
# -------------------------------

staticmethods = 0
for staticfile in os.listdir(STATIC_DIR):
    staticmethods += 1
    flaskapp.add_url_rule("/static/%s" % staticfile, endpoint="static%d" % staticmethods, view_func=lambda sf=staticfile : flaskapp.send_static_file(sf), methods=["GET"])
