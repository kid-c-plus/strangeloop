import flask
from .pedal import Pedal

pedal = Pedal()

flaskapp = flask.Flask(__name__)
# flaskapp.config.from_object("config")

from app import views
