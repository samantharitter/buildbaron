"""
This script runs the www application using a development server.
"""

from os import environ
from www import app
from flask import g

import sys
import os
import hashlib
import binascii
import datetime
import dateutil.parser

if __name__ == "__main__" and __package__ is None:
    lib_path = os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))
    print(lib_path)
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
    print(sys.path)

import analyzer

if __name__ == '__main__':
    HOST = environ.get('SERVER_HOST', 'localhost')
    try:
        PORT = int(environ.get('SERVER_PORT', '5555'))
    except ValueError:
        PORT = 5555

    # Various filters for Jinja 2
    #
    def format_log(s):
        return s.replace("\n", "<br/>")

    app.jinja_env.filters['format_log'] = format_log

    def hash_name(s):
        a = s.replace("\\", "_").replace("/", "_")
        m = hashlib.sha1()
        m.update(a.encode())
        digest = m.digest()
        digest64 = binascii.b2a_hex(digest).decode()
        return digest64

    app.jinja_env.filters['hash_name'] = hash_name

    def tohtml_logurl(s):
        idx = s.find("?")
        if idx != -1:
            s = s[:idx]
        return s

    app.jinja_env.filters['tohtml_logurl'] = tohtml_logurl

    def format_date(d):
        # Example: 2015-04-14T16:05:07.000+0000
        return dateutil.parser.parse(d).strftime("%b %e, %Y")

    app.jinja_env.filters['date'] = format_date

    app.config["TEMPLATES_AUTO_RELOAD"] = True

    app.run(HOST, PORT, debug=False)
