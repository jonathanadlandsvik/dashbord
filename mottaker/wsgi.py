# WSGI-oppsett for PythonAnywhere.
# Innholdet her skal limes inn i WSGI-filen under Web-fanen
# (/var/www/jonathwa_pythonanywhere_com_wsgi.py).

import os
import sys

project_home = '/home/jonathwa/mysite'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Les API-nøklene fra /home/jonathwa/mysite/.env.
# Filen ligger bare på serveren og skal aldri inn i git.
env_fil = os.path.join(project_home, '.env')
if os.path.exists(env_fil):
    with open(env_fil) as f:
        for linje in f:
            linje = linje.strip()
            if linje and not linje.startswith('#') and '=' in linje:
                navn, verdi = linje.split('=', 1)
                os.environ.setdefault(navn.strip(), verdi.strip())

# import flask app but need to call it "application" for WSGI to work
from flask_app import app as application  # noqa
