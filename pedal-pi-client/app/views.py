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

SUCCESS_CODE        = 200
BAD_REQUEST_CODE    = 400
SERVER_ERROR_CODE   = 500

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
    nickname = flask.request.values['nickname']
    if nickname:
        nickname = str(nickname)
        serverresponse = pedal.newsession(nickname)
        return flask.make_response(flask.jsonify(serverresponse), 200 if serverresponse == SUCCESS_RETURN else 500) 
    else:
        return flask.make_response(flask.jsonify(FAILURE_RETURN), 400)

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    sessionid = flask.request.values['sessionid']
    nickname = flask.request.values['nickname']
    if sessionid and nickname:
        sessionid = str(sessionid)
        nickname = str(nickname)
        serverresponse = pedal.joinsession(nickname, sessionid)
        return flask.make_response(flask.jsonify(serverresponse), 200 if serverresponse == SUCCESS_RETURN else 500)
    else:
        return flask.make_response(flask.jsonify(FAILURE_RETURN), 400)

@flaskapp.route("/endsession", methods=["POST"])
def endsession():
    serverresponse = pedal.endsession()
    return flask.make_response(flask.jsonify(serverresponse), 200 if serverresponse == SUCCESS_RETURN else 500)

@flaskapp.route("/leavesession", methods=["POST"])
def leavesession():
    serverresponse = pedal.leavesession()
    return flask.make_response(flask.jsonify(serverresponse), 200 if serverresponse == SUCCESS_RETURN else 500)

@flaskapp.route("/toggleloop", methods=["POST"])
def toggleloop():
    if pedal.recording:
        serverresponse = pedal.endloop()
    else:
        serverresponse = pedal.startloop()
    return flask.make_response(flask.jsonify(serverresponse), 200 if serverresponse == SUCCESS_RETURN else 500)
    

# ------------------------------
#   Asynchronous GET endpoints
# ------------------------------

# check current session membership
@flaskapp.route("/getsession")
def getsession():
    serverresponse = pedal.getsession()
    if serverresponse == SUCCESS_RETURN:
        return flask.make_response(flask.jsonify(pedal.sessionid, pedal.owner), 200)
    else:
        return flask.make_response(flask.jsonify(serverresponse), 500)

# get list of session members
@flaskapp.route("/getmembers")
def getmembers():
    serverresponse = pedal.getmembers()
    if serverresponse == SUCCESS_RETURN:
        return flask.make_response(flask.jsonify(pedal.sessionmembers), 200)
    else:
        return flask.make_response(flask.jsonify(serverresponse), 500)

# get list of loop ids
# this one does NOT incur an "updateloops" call from the pedal because that involves a lot of data
# instead just returns all the keys from offline loop dict
@flaskapp.route("/getloops")
def getloops():
    return flask.make_response(flask.jsonify(sorted(list(pedal.loops.keys()))), 200)

# -------------------------------
#   Static Fileserver Endpoints
# -------------------------------

staticmethods = 0
for staticfile in os.listdir(STATIC_DIR):
    staticmethods += 1
    flaskapp.add_url_rule("/static/%s" % staticfile, endpoint="static%d" % staticmethods, view_func=lambda sf=staticfile : flaskapp.send_static_file(sf), methods=["GET"])
