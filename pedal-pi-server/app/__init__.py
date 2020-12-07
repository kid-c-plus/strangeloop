import flask
import flask_sqlalchemy
from datetime import datetime as dt, timedelta as td
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# -------------
#   Constants
# -------------

# max idle time for a session before deletion (in hours)
MAX_SESSION_IDLE = 4

# interval for running database maintenance method
DB_MAINTENANCE_INTERVAL = {'hours' : 1}

# -------------------------------
#   Object Factory Init Actions
# -------------------------------

flaskapp = flask.Flask(__name__)
flaskapp.config.from_object("config")
db = flask_sqlalchemy.SQLAlchemy(flaskapp)

idle_td = td(hours=MAX_SESSION_IDLE)

# --------------------------------
#   Database Maintenance Methods
# --------------------------------

# delete orphaned and idle sessions (where no new loop has been submitted in the past MAX_SESSION_IDLE hours)
def maintaindatabase():
    sessions = models.Session.query.all()
    for session in sessions:
        if not len(session.pedals) or session.lastmodified < dt.utcnow() - idle_td:
            flaskapp.logger.info("Deleted %s session %s at %s" % ("idle" if len(session.pedals) else "orphaned", session.id, dt.now()))
            db.session.delete(session)

        db.session.commit()

# schedule maintaindatabase to run at DB_MAINTENANCE_INTERVAL
dbsched = BackgroundScheduler()
dbsched.add_job(func=maintaindatabase, trigger="interval", **DB_MAINTENANCE_INTERVAL)
dbsched.start()

# end scheduled tasks at object deinit
atexit.register(dbsched.shutdown)

from app import views, models
