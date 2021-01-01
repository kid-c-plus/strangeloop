import logging
import sys
import flask
import flask_cors
from .pedal import Pedal

flaskapp = flask.Flask(__name__)
flaskapp.config.from_object("config")

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s():%(lineno)d - %(message)s'))
flaskapp.logger.handlers.clear()
flaskapp.logger.addHandler(handler)
flaskapp.logger.setLevel(logging.DEBUG)

pedal = Pedal(debug=True, createsession=False, loggername="%s.pedal" % __name__)
pedal.run()

cors = flask_cors.CORS(flaskapp, origins=["http://%s" %  pedal.domainname, "http://%s" % pedal.ipaddress])

from app import views
