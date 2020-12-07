import logging
import sys
import flask
from .pedal import Pedal

pedal = Pedal(debug=True, webdebug=True, loggername="%s.pedal" % __name__)

flaskapp = flask.Flask(__name__)
flaskapp.config.from_object("config")

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s():%(lineno)d - %(message)s'))
flaskapp.logger.handlers.clear()
flaskapp.logger.addHandler(handler)
flaskapp.logger.setLevel(logging.DEBUG)

from app import views
