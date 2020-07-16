import flask
import flask_sqlalchemy

flaskapp = flask.Flask(__name__)
flaskapp.config.from_object("config")
db = flask_sqlalchemy.SQLAlchemy(flaskapp)

from app import views, models
