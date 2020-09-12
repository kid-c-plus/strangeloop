#!/usr/local/bin/python3
from app import flaskapp, pedal
from threading import Thread
import webbrowser

processaudiothread = Thread(target=pedal.processaudio, daemon=True)
processaudiothread.start()

flaskapp.run(host="0.0.0.0", port=80, debug=True)

webbrowser.open("http://localhost")
