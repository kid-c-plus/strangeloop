#!/usr/local/bin/python3
from app import flaskapp, db

meta = db.metadata
for table in reversed(meta.sorted_tables):
    db.session.execute(table.delete())
db.session.commit()

flaskapp.run(debug=True)
