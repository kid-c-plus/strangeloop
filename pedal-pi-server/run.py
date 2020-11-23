#!/usr/local/bin/python3
import sys
sys.path.append("../common")
from app import flaskapp, db

meta = db.metadata
for table in reversed(meta.sorted_tables):
    db.session.execute(table.delete())
db.session.commit()

flaskapp.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
