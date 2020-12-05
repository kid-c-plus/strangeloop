import flask
from .pedal import Pedal

pedal = Pedal(debug=True)

flaskapp = flask.Flask(__name__)
flaskapp.config.from_object("config")

from app import views
