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

import time
from bsddb3.db import DB_SET_RANGE
from simple_profiler import SimpleProfiler

prof = SimpleProfiler()

request_start = time.time_ns()

with prof.measure_block("imports"):
    import cgi
    from urllib import parse
    import sys
    import os

# Get values from http GET
form = cgi.FieldStorage()
query_string = form.getvalue('q')
query_family = form.getvalue('f')
query_project = form.getvalue('p')

# Get project dirs
basedir = os.environ['LXR_PROJ_DIR']
datadir = basedir + '/' + query_project + '/data'
repodir = basedir + '/' + query_project + '/repo'

with prof.measure_block("query_init"):
    # Import query
    sys.path = [ sys.path[0] + '/..' ] + sys.path
    from query import Query
    from lib import autoBytes
    q = Query(datadir, repodir)

# Create tmp directory for autocomplete
tmpdir = '/tmp/autocomplete/' + query_project
if not(os.path.isdir(tmpdir)):
    os.makedirs(tmpdir, exist_ok=True)

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

# Init values for tmp files
#filename = tmpdir + '/' + name
#mode = 'r+' if os.path.exists(filename) else 'w+'

"""
# Open tmp file
# Fill it with the keys of the database only
# if the file is older than the database
f = open(filename, mode)
if not f.readline()[:-1] == latest:
    with prof.measure_block("tmp_write"):
        prof.set_category(f"tmp_write_{query_project}")
        f.seek(0)
        f.truncate()
        f.write(latest + "\n")
        f.write('\n'.join([process(x.decode()) for x in q.query('keys', name)]))
        f.seek(0)
        f.readline() # Skip first line that store the version number
else:
    prof.set_category(f"no_tmp_write_{query_project}")
"""

prof.set_category(f"improved_{query_project}")

# Prepare http response
response = 'Content-Type: text/html;charset=utf-8\n\n[\n'

i = 0
cur = db.db.cursor()
query_bytes = autoBytes(query_string)
key, _ = cur.get(query_bytes, DB_SET_RANGE)
while i <= 10:
    if key.startswith(query_bytes):
        i += 1
        response += '"' + key.decode("utf-8") + '",'
        key, _ = cur.next()
    else:
        break

"""
with prof.measure_block("search"):
    # Search for the 10 first matching elements in the tmp file
    index = 0
    for i in f:
        if i.startswith(query_string):
            response += '"' + i[:-1] + '",'
            index += 1

        if index == 10:
            break
"""

# Complete and send response
response = response[:-1] + ']'
print(response)

# Close tmp file
#f.close()

prof.set_total(time.time_ns() - request_start)
prof.log_to_file("/tmp/elixir-autocomplete-profiler")
