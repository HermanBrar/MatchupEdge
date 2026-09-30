"""Tests never use the developer database or locally configured API key."""
import os
import tempfile
import atexit
from pathlib import Path

_temp = tempfile.TemporaryDirectory(prefix='matchupedge-tests-')
atexit.register(_temp.cleanup)
os.environ['APP_MODE'] = 'demo'
os.environ['ODDS_API_KEY'] = ''
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_temp.name) / 'test.db')
