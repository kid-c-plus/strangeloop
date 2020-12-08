from app import flaskapp, db, models

import flask
import json
from string import ascii_uppercase
from datetime import datetime as dt
from io import BytesIO
import numpy as np
import re
import random

import sys
sys.path.append("../../common")
from common import *

# -------------
#   Constants
# -------------

# MAX_SESSIONS = 52 ** 4
MAX_SESSIONS = 200
MAX_SESSION_SIZE = 20
MAX_LOOPS = 30

MAC_REGEX = re.compile("(..:){5}..")
NICKNAME_SUB_REGEX = re.compile("[,\n]")

# ------------------
#   Helper Methods
# ------------------

# generate random 4-character session ID

def generatesessionid(seed=0):
    sessionid = ""
    for _ in range(4):
        sessionid = ascii_uppercase[seed % 26] + sessionid
        seed //= 26
    return sessionid

# --------------------
#   Server Endpoints
# --------------------

# --------------------------------
#   Session Management Endpoints
# --------------------------------

# create new session
# args:     POST: MAC address of pedal requesting new session
#           POST: nickname of pedal
# return:   SUCCESS_RETURN if session created, FULL_RETURN if server is full, or FAILURE_RETURN if pedal already in session

@flaskapp.route("/newsession", methods=["POST"])
def newsession():
    mac, nickname = [flask.request.values.get(key) for key in ('mac', 'nickname')]
    if mac and MAC_REGEX.fullmatch(str(mac)) and nickname:
        mac, nickname = [str(val) for val in (mac, nickname)]
        nickname = NICKNAME_SUB_REGEX.sub("", nickname)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            # pedal already has running session
            flaskapp.logger.info("Pedal %s at IP %s requested new session despite already having open session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
            return NONE_RETURN 
        else:
            numsessions = models.Pedal.query.count()
            if numsessions < MAX_SESSIONS: 
                sessionid = generatesessionid(random.randint(0, 52 ** 4 - 1))
                while models.Session.query.get(sessionid):
                    sessionid = generatesessionid(random.randint(0, 52 ** 4 - 1))
                session = models.Session(id=sessionid, timestamp=dt.utcnow(), ownermac=mac)
                db.session.add(session)
        
                if pedal:
                    pedal.session = session
                else:
                    pedal = models.Pedal(mac=mac.strip(), nickname=nickname.strip(), session=session)
                    db.session.add(pedal)
                
                db.session.commit()
                flaskapp.logger.info("Session %s created for pedal %s at IP %s" % (sessionid, mac, flask.request.remote_addr))
                return SUCCESS_RETURN
            else:
                flaskapp.logger.info("Pedal %s at IP %s requested session from full server" % (mac, flask.request.remote_addr))
                return FULL_RETURN
    else:
        flaskapp.logger.info("Received incomplete new session request from IP %s: MAC? %r, Nickname? %r" % (flask.request.remote_addr, bool(mac), bool(nickname)))
        return FAILURE_RETURN
    
    
# end session
# args:     POST: MAC address of pedal ending session
# return:   SUCCESS_RETURN if session closed, FAILURE_RETURN if requester not session owner or session nonexistent

@flaskapp.route("/endsession", methods=["POST"])
def endsession():
    mac = flask.request.values.get('mac')
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            if pedal.session.ownermac == mac:
                flaskapp.logger.info("Pedal %s at IP %s has ended session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
                db.session.delete(pedal.session)

                db.session.commit()
            
                return SUCCESS_RETURN
            else:
                flaskapp.logger.info("Pedal %s at IP %s attempted to end session %s owned by %s" % (mac, flask.request.remote_addr, pedal.sessionid, pedal.session.ownermac))
                return FAILURE_RETURN
        else:
            flaskapp.logger.info("Received session end request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received end session request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN

# join session
# args:     POST: MAC address of pedal joining session
#           POST: nickname of pedal (optional)
#           POST: session ID to join
# return:   SUCCESS_RETURN if session joined, FAILURE_RETURN if session nonexistent or pedal already in session

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    mac, nickname, sessionid = [flask.request.values.get(key) for key in ('mac', 'nickname', 'sessionid')]
    if mac and MAC_REGEX.fullmatch(str(mac)) and nickname and sessionid:
        mac, nickname, sessionid = [str(val) for val in (mac, nickname, sessionid)]
        nickname = NICKNAME_SUB_REGEX.sub("", nickname)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            flaskapp.logger.info("Pedal %s at IP %s attempted to join session %s despite already being in session %s" % (mac, flask.request.remote_addr, sessionid, pedal.sessionid))
            return FAILURE_RETURN
        else:
            session = models.Session.query.get(sessionid)
            if session:
                if len(session.pedals) < MAX_SESSION_SIZE:
                    pedal = models.Pedal.query.get(mac)
                    if pedal:
                        pedal.session = session
                    else:
                        pedal = models.Pedal(mac=mac.strip(), nickname=nickname.strip(), session=session)

                    db.session.commit()

                    flaskapp.logger.info("Pedal %s at IP %s joined session %s" % (mac, flask.request.remote_addr, sessionid))
                    return SUCCESS_RETURN
                else:
                    flaskapp.logger.info("Pedal %s at IP %s attempted to join full session %s" % (mac, flask.request.remote_addr, sessionid))
                    return FULL_RETURN
            else:
                flaskapp.logger.info("Pedal %s at IP %s attempted to join non-existent session %s" % (mac, flask.request.remote_addr, sessionid))
                return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received incomplete join session request from IP %s: MAC? %r, Nickname? %r, Session ID? %r" % (flask.request.remote_addr, bool(mac), bool(nickname), bool(sessionid)))
        return FAILURE_RETURN

# leave session (without ending it)
# if session is empty after this, it is closed
# args:     POST: MAC address of pedal ending session
# return:   SUCCESS_RETURN if session left, FAILURE_RETURN if not in any session

@flaskapp.route("/leavesession", methods=["POST"])
def leavesession():
    mac = flask.request.values.get('mac')
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            session = pedal.session

            db.session.delete(pedal)
            
            db.session.commit()

            flaskapp.logger.info("Pedal %s at IP %s has left session %s" % (mac, flask.request.remote_addr, session.id))
            if not len(session.pedals):
                flaskapp.logger.info("Empty session %s has been closed" % session.id)

                db.session.delete(session)

                db.session.commit()

            return SUCCESS_RETURN
        else:
            flaskapp.logger.info("Received leave session request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received leave session request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN

# check current session status
# args:     POST: MAC address of pedal checking session
# return:   owner/member and current session, or NONE_RETURN if unsessioned

@flaskapp.route("/getsession", methods=["POST"])
def getsession():
    mac = flask.request.values.get('mac')
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            flaskapp.logger.info("Received get session request from pedal %s at IP %s in session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
            return "%s:%s" % ("owner" if pedal.session.ownermac == mac else "member", pedal.sessionid)
        else:
            flaskapp.logger.info("Received get session request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return NONE_RETURN
    else:
        flaskapp.logger.info("Received get session request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN

# ---------------------------------
#   Session Interaction Endpoints
# ---------------------------------

# get list of pedal nicknames for given session
# args:     POST: MAC addres of requesting pedal
# return:   list of pedals in session, or NONE_RETURN if pedal unsessioned

@flaskapp.route("/getmembers", methods=["POST"])
def getmembers():
    mac = flask.request.values.get('mac')
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            flaskapp.logger.info("Pedal %s at IP %s has requested member list for session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
            return ",".join([pedal.nickname for pedal in models.Session.query.get(pedal.sessionid).pedals])
        else:
            flaskapp.logger.info("Received membership list request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return NONE_RETURN
    else:
        flaskapp.logger.info("Received membership list request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN

# get list of loop ids previously added by this pedal, so that it can continue providing device-unique ids
# args:     POST: MAC addres of requesting pedal
# return:   list of loop ids from this pedal in session, or NONE_RETURN if pedal unsessioned

@flaskapp.route("/getloopids", methods=["POST"])
def getloopids():
    mac = flask.request.values.get('mac')
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            flaskapp.logger.info("Pedal %s at IP %s has requested loop list for session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
            return ",".join([loop.index for loop in models.Session.query.get(pedal.sessionid).loops])
        else:
            flaskapp.logger.info("Received loop list request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return NONE_RETURN
    else:
        flaskapp.logger.info("Received loop list request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN


# add loop to session
# args:     POST: MAC address of pedal sending loop 
#           POST: index of new loop 
#           POST: data representing numpy representation of loop recording
# return:   true if loop added, false if index already present from given mac, or if pedal unsessioned

@flaskapp.route("/addloop", methods=["POST"])
def addloop():
    mac, index = [flask.request.values.get(key) for key in ('mac', 'index')]
    npdata = flask.request.files.get('npdata').read()
    if mac and MAC_REGEX.fullmatch(str(mac)) and index and npdata:
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            if len(pedal.session.loops) < MAX_LOOPS:
                if models.Loop.query.get((mac, index)):
                    flaskapp.logger.info("Pedal %s at IP %s attempted to add loop to session %s at already-present index %s" % (mac, flask.request.remote_addr, pedal.sessionid, index))
                    return FAILURE_RETURN
                else:
                    flaskapp.logger.info("Pedal %s at IP %s added a new loop to session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
                
                    loop = models.Loop(pedalmac=mac, index=index, timestamp=dt.utcnow(), npdata=npdata, session=pedal.session)

                    pedal.session.generatecomposite(fromscratch=False)
                    pedal.session.lastmodified = dt.utcnow()
                    
                    db.session.commit()
                    return SUCCESS_RETURN
            else:
                flaskapp.logger.info("Pedal %s at IP %s attempted to add loop to full session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
                return FULL_RETURN
        else:
            flaskapp.logger.info("Received add loop request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received incomplete add loop request from IP %s: MAC? %r, index? %r, raw data? %r" % (flask.request.remote_addr, bool(mac), bool(index), bool(npdata)))
        return FAILURE_RETURN

# remove loop from session
# args:     POST: MAC address of pedal removing loop 
#           POST: index of loop to remove
# return:   SUCCESS_RETURN if loop removed, FAILURE_RETURN if no loop at index + mac of pedal or if pedal unsessioned

@flaskapp.route("/removeloop", methods=["POST"])
def removeloop():
    mac, index = [flask.request.values.get(key) for key in ('mac', 'index')]
    if mac and MAC_REGEX.fullmatch(str(mac)) and index:
        mac, index = [str(val) for val in (mac, index)]
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            loop = models.Loop.query.get((mac, index))
            if loop:
                db.session.delete(loop)

                flaskapp.logger.info("Pedal %s at IP %s removed loop %s from session %s" % (mac, flask.request.remote_addr, index, pedal.sessionid))

                db.session.commit()

                pedal.session.generatecomposite(fromscratch=True)
                pedal.session.lastmodified = dt.utcnow()

                db.session.commit()
                
                return SUCCESS_RETURN
            else:
                flaskapp.logger.info("Pedal %s at IP %s attempted to remove nonexistent loop %s from session %s" % (mac, flask.request.remote_addr, index, pedal.sessionid))
                return FAILURE_RETURN
        else:
            flaskapp.logger.info("Received remove loop request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received incomplete remove loop request from IP %s: MAC? %r, index? %r" % (flask.request.remote_addr, bool(mac), bool(index)))
        return FAILURE_RETURN

# get current composite
# this is the method clients use for polling
# args:     POST: MAC address of pedal requesting composite 
#           POST: timestamp of last update (can be null)
# return:   raw data if update necessary, NONE_RETURN if no updates since provided timestamp or unsessioned

@flaskapp.route("/getcomposite", methods=["POST"])
def getcomposite():
    mac, timestamp = [flask.request.values.get(key) for key in ('mac', 'timestamp')]
    if mac and MAC_REGEX.fullmatch(str(mac)):
        mac = str(mac)
        pedal = models.Pedal.query.get(mac)
        if pedal and pedal.session:
            if pedal.session.composite:
                if timestamp and timestamp != "None":
                    flaskapp.logger.info("Pedal %s at IP %s has requested composite from %s for session %s" % (mac, flask.request.remote_addr, timestamp, pedal.sessionid))
                    try:
                        timestamp = float(timestamp)
                    except:
                        flaskapp.logger.info("Received invalid timestamp from pedal %s at IP %s" % (mac, flask.request.remote_addr))
                        return FALSE_RETURN
                    flaskapp.logger.info("timestamp: %f, pedal.session.lastmodified: %f" % (timestamp, pedal.session.lastmodified.timestamp()))
                    if timestamp < pedal.session.lastmodified.timestamp():
                        return flask.Response(pedal.session.composite)
                    else:
                        return NONE_RETURN
                else:
                    flaskapp.logger.info("Pedal %s at IP %s has requested composite without timestamp for session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
                    flaskapp.logger.info("Sending composite...")
                    return flask.Response(pedal.session.composite)
            else:
                flaskapp.logger.info("Pedal %s at IP %s has received empty composite for session %s" % (mac, flask.request.remote_addr, pedal.sessionid))
                return EMPTY_RETURN
        else:
            flaskapp.logger.info("Received composite request from unsessioned pedal %s at IP %s" % (mac, flask.request.remote_addr))
            return FAILURE_RETURN
    else:
        flaskapp.logger.info("Received composite request without MAC address from IP %s" % flask.request.remote_addr)
        return FAILURE_RETURN
