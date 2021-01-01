from app import flaskapp, pedal
import flask
import json
import os

import sys
sys.path.append("opt/strangeloop/common")
from common import *

# -------------
#   Constants
# -------------

# directory containing static web GUI resource files
STATIC_DIR = "/opt/strangeloop/pedal-pi-client/app/static/dist"

# HTTP response codes
SUCCESS_CODE        = 200
FAILURE_CODE        = 404
BAD_REQUEST_CODE    = 400

# --------------------------------
#   Client-Server Endpoints
# --------------------------------

@flaskapp.route("/")
def index():
    return flask.render_template("index.html", pedal=pedal)
 
# -------------------------------
#   Asynchronous POST endpoints
# -------------------------------

@flaskapp.route("/newsession", methods=["POST"])
def newsession():
    nickname = flask.request.json['nickname']
    if nickname:
        nickname = str(nickname)
        pedalresponse = pedal.newsession(nickname)
        return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE) 
    else:
        return flask.make_response(flask.jsonify(FAILURE_RETURN), BAD_REQUEST_CODE)

@flaskapp.route("/endsession", methods=["POST"])
def endsession():
    pedalresponse = pedal.endsession()
    return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    sessionid = flask.request.json['sessionid']
    nickname = flask.request.json['nickname']
    if sessionid and nickname:
        sessionid = str(sessionid)
        nickname = str(nickname)
        pedalresponse = pedal.joinsession(nickname, sessionid)
        return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)
    else:
        return flask.make_response(flask.jsonify(FAILURE_RETURN), BAD_REQUEST_CODE)

@flaskapp.route("/leavesession", methods=["POST"])
def leavesession():
    pedalresponse = pedal.leavesession()
    return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)

@flaskapp.route("/toggleloop", methods=["POST"])
def toggleloop():
    if pedal.recording:
        pedalresponse = pedal.endloop()
    else:
        pedalresponse = pedal.startloop()
    return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)

@flaskapp.route("/removeloop", methods=["POST"])
def removeloop():
    loopindex = flask.request.json['loopindex']
    if loopindex:
        try:
            loopindex = int(loopindex)
            pedalresponse = pedal.removeloop(loopindex)
            return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)
        except:
            pass
    return flask.make_response(flask.jsonify(FAILURE_RETURN), BAD_REQUEST_CODE)
            

@flaskapp.route("/startplayback", methods=["POST"])
    loopindex = flask.request.json['loopindex']
    if loopindex:
        try:
            loopindex = int(loopindex)
            pedalresponse = pedal.startplayback(loopindex)
            return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)
        except:
            pass
    return flask.make_response(flask.jsonify(FAILURE_RETURN), BAD_REQUEST_CODE)

@flaskapp.route("/stopplayback", methods=["POST"])
    pedalresponse = pedal.stopplayback()
    return flask.make_response(flask.jsonify(pedalresponse), SUCCESS_CODE if pedalresponse == SUCCESS_RETURN else FAILURE_CODE)

# ------------------------------
#   Asynchronous GET endpoints
# ------------------------------

# check current session membership
@flaskapp.route("/getsession")
def getsession():
    pedalresponse = pedal.getsession()
    if pedalresponse in [SUCCESS_RETURN, NONE_RETURN]:
        return flask.make_response(flask.jsonify((pedal.sessionid, pedal.owner)), SUCCESS_CODE)
    else:
        return flask.make_response(flask.jsonify(pedalresponse), FAILURE_CODE)

# get list of session members
@flaskapp.route("/getmembers")
def getmembers():
    pedalresponse = pedal.getmembers()
    if pedalresponse in [SUCCESS_RETURN, NONE_RETURN]:
        return flask.make_response(flask.jsonify(pedal.sessionmembers), SUCCESS_CODE)
    else:
        return flask.make_response(flask.jsonify(pedalresponse), FAILURE_CODE)

# get list of loop ids
# this one does NOT incur an "updateloops" call from the pedal because that involves a lot of data
# instead just returns all the keys from offline loop dict
@flaskapp.route("/getloops")
def getloops():
    return flask.make_response(flask.jsonify(sorted(list(pedal.loops.keys()))), SUCCESS_CODE)

# -------------------------------
#   Static Fileserver Endpoints
# -------------------------------

staticmethods = 0
for staticfile in os.listdir(STATIC_DIR):
    staticmethods += 1
    flaskapp.add_url_rule("/static/%s" % staticfile, endpoint="static%d" % staticmethods, view_func=lambda sf=staticfile : flaskapp.send_static_file(sf), methods=["GET"])
