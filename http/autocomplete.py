#!/usr/bin/env python3

#  This file is part of Elixir, a source code cross-referencer.
#
#  Copyright (C) 2017--2020 Maxime Chretien <maxime.chretien@bootlin.com>
#                           and contributors.
#
#  Elixir is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Elixir is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with Elixir.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import json
from urllib import parse
from bsddb3.db import DB_SET_RANGE
import falcon

ELIXIR_DIR = os.path.dirname(os.path.realpath(__file__)) + '/..'

if ELIXIR_DIR not in sys.path:
    sys.path = [ ELIXIR_DIR ] + sys.path

import query
from lib import autoBytes

class AutocompleteResource:
    def on_get(self, req, resp):
        # Get values from http GET
        query_string = req.get_param('q')
        query_family = req.get_param('f')
        query_project = req.get_param('p')

        # Get project dirs
        basedir = req.env['LXR_PROJ_DIR']
        datadir = basedir + '/' + query_project + '/data'
        repodir = basedir + '/' + query_project + '/repo'

        q = query.Query(datadir, repodir)

        latest = q.query('latest')

        # Define some specific values for some families
        if query_family == 'B':
            name = 'comps'
            process = lambda x: parse.unquote(x)
            db = q.db.comps
        else:
            name = 'defs'
            process = lambda x: x
            db = q.db.defs

        response = []

        # Search for the 10 first matching elements in the tmp file
        i = 0
        cur = db.db.cursor()
        query_bytes = autoBytes(query_string)
        key, _ = cur.get(query_bytes, DB_SET_RANGE)
        while i <= 10:
            if key.startswith(query_bytes):
                i += 1
                response.append(process(key.decode("utf-8")))
                key, _ = cur.next()
            else:
                break

        resp.text = json.dumps(response)
        resp.status = falcon.HTTP_200
        resp.content_type = falcon.MEDIA_JSON


def get_application():
    app = falcon.App()
    app.add_route('/', AutocompleteResource())
    return app

application = get_application()

