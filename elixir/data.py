#!/usr/bin/env python3

#  This file is part of Elixir, a source code cross-referencer.
#
#  Copyright (C) 2017--2020 Mikaël Bouillot <mikael.bouillot@bootlin.com>
#  and contributors
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

import re
import os
import os.path
import errno
from urllib import parse
import bsddb3
import bsddb3.db

deflist_regex = re.compile(b'(\d*)(\w)(\d*)(\w),?')
deflist_macro_regex = re.compile('\dM\d+(\w)')

##################################################################################

defTypeR = {
    'c': 'config',
    'd': 'define',
    'e': 'enum',
    'E': 'enumerator',
    'f': 'function',
    'l': 'label',
    'M': 'macro',
    'm': 'member',
    'p': 'prototype',
    's': 'struct',
    't': 'typedef',
    'u': 'union',
    'v': 'variable',
    'x': 'externvar'}

defTypeD = {v: k for k, v in defTypeR.items()}

##################################################################################

maxId = 999999999

class DefList:
    '''Stores associations between a blob ID, a type (e.g., "function"),
        a line number and a file family.
        Also stores in which families the ident exists for faster tests.'''
    def __init__(self, data=b'#'):
        self.data, self.families = data.split(b'#')

    def iter(self, dummy=False):
        # Get all element in a list of sublists and sort them
        entries = deflist_regex.findall(self.data)
        entries.sort(key=lambda x:int(x[0]))
        for id, type, line, family in entries:
            id = int(id)
            type = defTypeR [type.decode()]
            line = int(line)
            family = family.decode()
            yield id, type, line, family
        if dummy:
            yield maxId, None, None, None

    def append(self, id, type, line, family):
        if type not in defTypeD:
            return
        p = str(id) + defTypeD[type] + str(line) + family
        if self.data != b'':
            p = ',' + p
        self.data += p.encode()
        self.add_family(family)

    def pack(self):
        return self.data + b'#' + self.families

    def add_family(self, family):
        family = family.encode()
        if not family in self.families.split(b','):
            if self.families != b'':
                family = b',' + family
            self.families += family

    def get_families(self):
        return self.families.decode().split(',')

    def get_macros(self):
        return deflist_macro_regex.findall(self.data.decode()) or ''

class PathList:
    '''Stores associations between a blob ID and a file path.
        Inserted by update.py sorted by blob ID.'''
    def __init__(self, data=b''):
        self.data = data

    def iter(self, dummy=False):
        for p in self.data.split(b'\n')[:-1]:
            id, path = p.split(b' ',maxsplit=1)
            id = int(id)
            path = path.decode()
            yield id, path
        if dummy:
            yield maxId, None

    def append(self, id, path):
        p = str(id).encode() + b' ' + path + b'\n'
        self.data += p

    def pack(self):
        return self.data

class RefList:
    '''Stores a mapping from blob ID to list of lines
        and the corresponding family.'''
    def __init__(self, data=b''):
        self.data = data

    def iter(self, dummy=False):
        # Split all elements in a list of sublists and sort them
        entries = [x.split(b':') for x in self.data.split(b'\n')[:-1]]
        entries.sort(key=lambda x:int(x[0]))
        for file_id, lines, family in entries:
            file_id = int(file_id.decode())
            lines= lines.decode()
            family= family.decode()
            yield file_id, lines, family
        if dummy:
            yield maxId, None, None

    def append(self, id, lines, family):
        p = str(id) + ':' + lines + ':' + family + '\n'
        self.data += p.encode()

    def pack(self):
        return self.data

# Converts to/from a *List class (declared above)
# Expects the class to have a constructor that accepts bytes, and a pack method that returns bytes
class ListConverter:
    def __init__(self, list_cls):
        self.list_cls = list_cls

    def from_bytes(self, value):
        return self.list_cls(value)

    def to_bytes(self, value):
        return value.pack()

# Converts bytes to/from an integer
class IntConverter:
    def to_bytes(self, value):
        return str(value).encode()

    def from_bytes(self, value):
        return int(value.decode())

# Converts bytes to/from a UTF-8 string
class StringConverter:
    def to_bytes(self, value):
        return value.encode()

    def from_bytes(self, value):
        return value.decode()

# Converts bytes to/from a UTF-8 string, quotes/unquotes when necessary
class QuotedStringConverter:
    def to_bytes(self, value):
        return parse.quote(value).encode()

    def from_bytes(self, value):
        return parse.unquote(value.decode())

# Auto converts a string to bytes but also accepts bytes, always converts to a string
class DefaultKeyConverter:
    def to_bytes(self, value):
        if type(value) is str:
            value = value.encode()
        return value

    def from_bytes(self, value):
        return value.decode()

# Does not do any conversions
class RawConverter:
    def to_bytes(self, value):
        return value

    def from_bytes(self, value):
        return value

class BsdDB:
    def __init__(self, filename, readonly, key_converter=DefaultKeyConverter(), value_converter=RawConverter()):
        self.filename = filename
        self.db = bsddb3.db.DB()
        self.value_converter = value_converter
        self.key_converter = key_converter

        if readonly:
            self.db.open(filename, flags=bsddb3.db.DB_RDONLY)
        else:
            self.db.open(filename,
                flags=bsddb3.db.DB_CREATE,
                mode=0o644,
                dbtype=bsddb3.db.DB_BTREE)

    def exists(self, key):
        key = self.key_converter.to_bytes(key)
        return self.db.exists(key)

    def get(self, key):
        key = self.key_converter.to_bytes(key)
        value = self.db.get(key)
        return self.value_converter.from_bytes(value)

    def get_keys(self):
        return self.db.keys()

    # Finds "the smallest key greater than or equal to the specified key"
    # https://docs.oracle.com/cd/E17276_01/html/api_reference/C/dbcget.html
    # In practice this should mean "the key that starts with provided prefix"
    # See docs about the default comparison function for B-Tree databases:
    # https://docs.oracle.com/cd/E17276_01/html/api_reference/C/dbset_bt_compare.html
    def iterate_from(self, key_prefix):
        cur = self.db.cursor()
        record = cur.get(self.key_converter.to_bytes(key_prefix), bsddb3.db.DB_SET_RANGE)
        while record:
            key, value = record
            yield self.key_converter.from_bytes(key), self.value_converter.from_bytes(value)
            record = cur.next()

    def put(self, key, val):
        key = self.key_converter.to_bytes(key)
        val = self.value_converter.to_bytes(val)
        self.put_raw(key, val)

    def put_raw_value(self, key, val: bytes):
        key = self.key_converter.to_bytes(key)
        self.put_raw(key, val)

    def put_raw(self, key: bytes, val: bytes):
        self.db.put(key, val)

    def sync(self):
        self.db.sync()

    def close(self):
        self.db.close()

class DB:
    def __init__(self, dir, readonly=True, dtscomp=False):
        if os.path.isdir(dir):
            self.dir = dir
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), dir)

        ro = readonly

        # Repo related variables. Currently it seems to only store the number of 
        #  indexed blobs, see numBlobs key. Not used outside of update.py
        self.vars = BsdDB(dir + '/variables.db', ro, StringConverter(), IntConverter())
        # Git blob hashes -> internal blob ids. Not used outside of update.py
        self.blob = BsdDB(dir + '/blobs.db', ro, RawConverter(), IntConverter())
        # Internal blob ids -> git blob hashes. Not used outside of update.py
        self.hash = BsdDB(dir + '/hashes.db', ro, IntConverter(), RawConverter())
        # Internal blob ids -> filenames. Not used outside of update.py
        self.file = BsdDB(dir + '/filenames.db', ro, IntConverter(), StringConverter())
        # Version name (tag) -> list of (internal blob id, file path) in that version.
        #  Used in latest and versions query, and to make definitions list faster.
        self.vers = BsdDB(dir + '/versions.db', ro, value_converter=ListConverter(PathList))
        # Identifier -> list of definitions (file id, type, line, family)
        self.defs = BsdDB(dir + '/definitions.db', ro, value_converter=ListConverter(DefList))
        # Identifier -> list of references (file id, lines, family)
        self.refs = BsdDB(dir + '/references.db', ro, value_converter=ListConverter(RefList))
        # Identifier -> list of doccoments (file id, lines, family)
        self.docs = BsdDB(dir + '/doccomments.db', ro, value_converter=ListConverter(RefList))
        self.dtscomp = dtscomp
        if dtscomp:
            # DTS identifier -> list of references (file id, lines, family)
            self.comps = BsdDB(dir + '/compatibledts.db', ro, QuotedKeyConverter(), ListConverter(RefList))
            # DTS identifier -> list of doccoments (file id, lines, family)
            self.comps_docs = BsdDB(dir + '/compatibledts_docs.db', ro, QuotedKeyConverter(), ListConverter(RefList))
            # Use a RefList in case there are multiple doc comments for an identifier

    def close(self):
        self.vars.close()
        self.blob.close()
        self.hash.close()
        self.file.close()
        self.vers.close()
        self.defs.close()
        self.refs.close()
        self.docs.close()
        if self.dtscomp:
            self.comps.close()
            self.comps_docs.close()
