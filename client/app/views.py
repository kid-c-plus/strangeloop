from app import flaskapp, pedal
import flask

# --------------------------------
#   Client-Server Endpoints
# --------------------------------

@flaskapp.route("/")
def index():
    return flask.render_template("index.html", pedal=pedal)

@flaskapp.route("/newsession", methods=["POST"])
def newsession():
    nickname = flask.request.values['nickname']
    if nickname:
        nickname = str(nickname)
        return pedal.newsession()

@flaskapp.route("/endsession", methods=["POST"])

@flaskapp.route("/joinsession", methods=["POST"])
def joinsession():
    sessionid = flask.request.values['sessionid']
    if sessionid:
        sessionid = str(sessionid)
        return pedal.joinsession(sessionid)

serverendpoints = ["newsession", "endsession", "leavesession", "getmembers", "startloop", "endloop", "getcomposite"]
for endpoint in serverendpoints:
    flaskapp.add_url_rule("/%s" % endpoint, endpoint, lambda : eval("pedal.%s" % endpoint)(); index(), methods=["POST"])
