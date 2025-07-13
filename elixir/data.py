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

from typing import OrderedDict, List, Tuple
import berkeleydb
import re
import time
from . import lib
from .lib import autoBytes
import os
import os.path
import errno

# Cache size used by the update script for the largest databases. Tuple of (gigabytes, bytes).
# https://docs.oracle.com/database/bdb181/html/api_reference/C/dbset_cachesize.html
# https://docs.oracle.com/database/bdb181/html/programmer_reference/general_am_conf.html#am_conf_cachesize
CACHESIZE = (0,1024*1024*512)

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

        self.modified = False
        self.entries = None
        self.to_append = []
        self.tmp_packs_to_append = []

    def populate_entries(self):
        entries_modified = False
        if self.entries is None:
            self.flush_tmp_packs()
            self.entries = [
                (int(d[0]), d[1], d[2], d[3])
                for d in deflist_regex.findall(self.data)
            ]
            entries_modified = True

        if len(self.to_append) != 0:
            # TODO convert to_append entries
            self.entries += self.to_append
            self.to_append = []
            entries_modified = True

        if entries_modified:
            self.entries.sort(key=lambda x:int(x[0]))

    def iter(self, dummy=False):
        # Get all element in a list of sublists and sort them
        if self.entries is None:
            self.populate_entries()

        for id, type, line, family in self.entries:
            yield id, defTypeR[type.decode()], int(line), family.decode()
        if dummy:
            yield maxId, None, None, None

    def exists(self, idx: int, line_num: int):
        if self.entries is None:
            self.populate_entries()

        for id, _, line, _ in self.entries:
            if id == idx and int(line) == line_num:
                return True

        return False

    def append(self, id: int, type, line: int, family: str):
        if type not in defTypeD:
            return

        self.modified = True
        if self.entries is None:
            self.to_append.append((id, defTypeD[type].encode(), str(line), family.encode()))
        else:
            self.entries.append((id, defTypeD[type].encode(), str(line), family.encode()))

        self.add_family(family)

    def pack_without_families(self) -> bytes:
        self.flush_tmp_packs()

        if self.entries is None:
            to_append = b",".join([
                str(arg[0]).encode() + arg[1] + str(arg[2]).encode() + arg[3]
                for arg in self.to_append
            ])
            self.to_append = []
            self.data += to_append
        else:
            self.data = b",".join([
                str(arg[0]).encode() + arg[1] + str(arg[2]).encode() + arg[3]
                for arg in self.entries
            ])
            self.entries = None

        return self.data

    def pack(self):
        return self.pack_without_families() + b'#' + self.families

    def tmp_pack(self) -> Tuple[bytes, List[bytes]]:
        # TODO what about sorting in update?
        return (self.pack_without_families(), self.families.split(b','))

    def add_tmp_pack(self, tmp_pack: Tuple[bytes, List[bytes]]):
        self.tmp_packs_to_append.append(tmp_pack)
        self.modified = True
    
    def flush_tmp_packs(self):
        if len(self.tmp_packs_to_append) == 0:
            return

        if self.entries is not None:
            self.pack_without_families()

        for tmp_pack in self.tmp_packs_to_append:
            data, families = tmp_pack

            for f in families:
                self.add_family_raw(f)

            if len(self.data) != 0:
                self.data += b','
                self.data += data
            else:
                self.data = data

        self.tmp_packs_to_append = []
        self.modified = True

    def add_family_raw(self, family: bytes):
        if not family in self.families.split(b','):
            self.families += b',' + family

    def add_family(self, family: str):
        if not family in self.families.split(b','):
            if self.families != b'':
                family = ',' + family
            self.families += family.encode()

    def get_families(self):
        return [f.decode() for f in self.families.split(b',')]

    def get_macros(self):
        return (deflist_macro_regex.findall(self.data.decode()) + [entry[1] for entry in self.to_append]) or ''

class PathList:
    '''Stores associations between a blob ID and a file path.
        Inserted by update.py sorted by blob ID.'''
    def __init__(self, data=b''):
        self.data = data
        self.modified = True
        self.to_append = []

    def iter(self, dummy=False):
        for p in self.data.split(b'\n')[:-1]:
            id, path = p.split(b' ',maxsplit=1)
            id = int(id)
            path = path.decode()
            yield id, path
        for id, path in self.to_append:
            yield id, path.decode()
        if dummy:
            yield maxId, None

    def append(self, id, path):
        self.to_append.append((id, path))

    def pack(self):
        if len(self.to_append) != 0:
            self.data += b'\n'.join((str(id).encode() + b' ' + path for id, path in self.to_append))
            self.data += b'\n'
            self.to_append = []

        return self.data

class RefList:
    '''Stores a mapping from blob ID to list of lines
        and the corresponding family.'''
    def __init__(self, data=b''):
        self.data = data
        self.entries = None
        self.to_append = []
        self.sorted = False
        self.modified = False

    def decode_entry(self, k):
        return (int(k[0].decode()), k[1].decode(), k[2].decode())

    def populate_entries(self):
        self.entries = [self.decode_entry(x.split(b':')) for x in self.data.split(b'\n')[:-1]]
        self.entries += self.to_append
        self.to_append = []
        self.entries.sort(key=lambda x:int(x[0]))

    def iter(self, dummy=False):
        if self.entries is None:
            self.populate_entries()

        for b, c, d in self.entries:
            yield b, c, d
        if dummy:
            yield maxId, None, None

    def append(self, id: int, lines: str, family: str):
        self.modified = True
        if self.entries is not None:
            self.entries.append((id, lines, family))
        else:
            self.to_append.append((id, lines, family))

    def pack(self):
        if self.entries is not None:
            assert len(self.to_append) == 0
            result = "".join([str(id) + ":" + lines + ":" + family + "\n" for id, lines, family in self.entries])
            self.entires = None
            self.data = result.encode()
            return self.data
        elif len(self.to_append) != 0:
            result = "".join([str(id) + ":" + lines + ":" + family + "\n" for id, lines, family in self.to_append])
            self.data += result.encode()
            self.to_append = []
            return self.data
        else:
            return self.data

    def pack_tmp(self) -> bytes:
        return self.pack()

    def add_tmp_pack(self, tmp_pack: bytes):
        self.pack()
        self.data += tmp_pack
        self.modified = True

class BsdDB:
    def __init__(self, filename, readonly, contentType, shared=False, cachesize=None):
        self.filename = filename
        self.db = berkeleydb.db.DB()
        self.flags = berkeleydb.db.DB_THREAD if shared else 0

        self.readonly = readonly
        if self.readonly:
            self.flags |= berkeleydb.db.DB_RDONLY
        else:
            self.flags |= berkeleydb.db.DB_CREATE

        if cachesize is not None:
            self.db.set_cachesize(cachesize[0], cachesize[1])

        self.open()
        self.ctype = contentType

    def open(self):
        if self.readonly:
            self.db.open(self.filename, flags=self.flags)
        else:
            self.db.open(self.filename, flags=self.flags, mode=0o644, dbtype=berkeleydb.db.DB_BTREE)

    def exists(self, key):
        key = autoBytes(key)
        return self.db.exists(key)

    def delete(self, key):
        key = autoBytes(key)
        return self.db.delete(key)

    def get(self, key):
        key = autoBytes(key)
        p = self.db.get(key)
        if p is None:
            return None
        p = self.ctype(p)
        return p

    def get_keys(self):
        return self.db.keys()

    def put(self, key, val, sync=False):
        key = autoBytes(key)
        val = autoBytes(val)
        if type(val) is not bytes:
            val = val.pack()
        self.db.put(key, val)
        if sync:
            self.db.sync()

    def sync(self):
        self.db.sync()
    
    def close(self):
        self.db.close()

    def __len__(self):
        return self.db.stat()["nkeys"]

class CachedBsdDB:
    def __init__(self, filename, readonly, contentType, cachesize, simple=False):
        self.filename = filename
        self.db = None
        self.readonly = readonly

        self.cachesize = cachesize
        self.cache = OrderedDict()

        self.open()

        self.ctype = contentType
        self.simple = simple

        self.raw_put_time = 0
        self.raw_get_time = 0
        self.raw_get_convert_time = 0
        self.raw_put_convert_time = 0
        self.append_time = 0

    def open(self):
        if self.db is None:
            self.db = berkeleydb.db.DB()
            self.db.set_cachesize(CACHESIZE[0], CACHESIZE[1])

        flags = 0

        if self.readonly:
            flags |= berkeleydb.db.DB_RDONLY
            self.db.open(self.filename, flags=flags)
        else:
            flags |= berkeleydb.db.DB_CREATE
            self.db.open(self.filename, flags=flags, mode=0o644, dbtype=berkeleydb.db.DB_BTREE)

    def exists(self, key):
        if key in self.cache:
            return True

        return self.db.exists(autoBytes(key))

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]

        start = time.time()
        p = self.db.get(autoBytes(key))
        self.raw_get_time += time.time()-start

        if p is None:
            return None

        start = time.time()
        p = self.ctype(p)
        self.raw_get_convert_time += time.time()-start

        self.cache[key] = p
        self.cache.move_to_end(key)
        self.flush_tail()

        return p

    def get_keys(self):
        self.sync()
        return self.db.keys()

    def put(self, key, val):
        if self.readonly:
            raise Exception("database is readonly")

        self.cache[key] = val
        self.cache.move_to_end(key)
        self.flush_tail()

    def put_raw(self, key, val, sync=False):
        if self.readonly:
            raise Exception("database is readonly")

        start = time.time()
        key = autoBytes(key)
        val = autoBytes(val)
        if type(val) is not bytes:
            val = val.pack()

        self.raw_put_convert_time += time.time()-start

        start = time.time()
        self.db.put(key, val)
        self.raw_put_time += time.time()-start

        if sync:
            self.db.sync()


    def flush_tail(self):
        if len(self.cache) > self.cachesize:
            to_flush = []
            start = time.time()
            for _ in range(self.cachesize//100):
                old_k, old_v = self.cache.popitem(last=False)
                if self.simple or old_v.modified:
                    to_flush.append((old_k, old_v))

            to_flush.sort(key=lambda x: x[0])
            for old_k, old_v in to_flush:
                self.put_raw(old_k, old_v)

            end = time.time()
            
            if len(to_flush) > 0 and end-start >= 0.5:
                print("flushing tail took", len(to_flush), end-start)

    def sync(self):
        start = time.time()
        if not self.readonly:
            to_flush = []
            for k, v in self.cache.items():
                if self.simple:
                    to_flush.append((k,v))
                elif v.modified:
                    v.modified = False
                    to_flush.append((k,v))

            to_flush.sort(key=lambda x: x[0])
            for k, v in to_flush:
                self.put_raw(k, v)

            print("synced", len(to_flush), "/", len(self.cache), time.time()-start)

        self.db.sync()

    def close(self):
        self.sync()
        self.db.close()
        self.db = None

    def __len__(self):
        return self.db.stat()["nkeys"]

class DB:
    def __init__(self, dir, readonly=True, dtscomp=False, shared=False, update_cache=None):
        if os.path.isdir(dir):
            self.dir = dir
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), dir)

        ro = readonly
        NOOP = lambda x: x

        if update_cache:
            db_cls = lambda dir, ro, ctype: CachedBsdDB(dir, ro, ctype, cachesize=update_cache)
        else:
            db_cls = lambda dir, ro, ctype: BsdDB(dir, ro, ctype, shared=shared)

        self.vars = BsdDB(dir + '/variables.db', ro, lambda x: int(x.decode()), shared=shared)
            # Key-value store of basic information
        self.blob = BsdDB(dir + '/blobs.db', ro, lambda x: int(x.decode()), shared=shared, cachesize=CACHESIZE)
            # Map hash to sequential integer serial number
        self.hash = BsdDB(dir + '/hashes.db', ro, lambda x: x, shared=shared, cachesize=CACHESIZE)
            # Map serial number back to hash
        self.file = BsdDB(dir + '/filenames.db', ro, lambda x: x.decode(), shared=shared, cachesize=CACHESIZE)
            # Map serial number to filename
        self.vers = BsdDB(dir + '/versions.db', ro, PathList, shared=shared)
        self.todo = BsdDB(dir + '/todo.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs = db_cls(dir + '/definitions.db', ro, DefList)
        self.defs_cache = {}
        self.defs_cache['C'] = BsdDB(dir + '/definitions-cache-C.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['K'] = BsdDB(dir + '/definitions-cache-K.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['D'] = BsdDB(dir + '/definitions-cache-D.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['M'] = BsdDB(dir + '/definitions-cache-M.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        assert sorted(self.defs_cache.keys()) == sorted(lib.CACHED_DEFINITIONS_FAMILIES)
        self.refs = db_cls(dir + '/references.db', ro, RefList)
        self.docs = db_cls(dir + '/doccomments.db', ro, RefList)
        self.dtscomp = dtscomp
        if dtscomp:
            self.comps = db_cls(dir + '/compatibledts.db', ro, RefList)
            self.comps_docs = db_cls(dir + '/compatibledts_docs.db', ro, RefList)
            # Use a RefList in case there are multiple doc comments for an identifier

    def close(self):
        self.vars.close()
        self.blob.close()
        self.hash.close()
        self.file.close()
        self.vers.close()
        self.defs.close()
        self.defs_cache['C'].close()
        self.defs_cache['K'].close()
        self.defs_cache['D'].close()
        self.defs_cache['M'].close()
        self.refs.close()
        self.docs.close()
        if self.dtscomp:
            self.comps.close()
            self.comps_docs.close()

class RelationsDB:
    def __init__(self, dir, readonly=True, dtscomp=False, shared=False, update_cache=None):
        if os.path.isdir(dir):
            self.dir = dir
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), dir)

        ro = readonly
        NOOP = lambda x: x

        if update_cache:
            db_cls = lambda dir, ro, ctype: CachedBsdDB(dir, ro, ctype, cachesize=update_cache)
        else:
            db_cls = lambda dir, ro, ctype: BsdDB(dir, ro, ctype, shared=shared)

        self.defs = db_cls(dir + '/definitions.db', ro, DefList)
        self.defs_cache = {}
        self.defs_cache['C'] = BsdDB(dir + '/definitions-cache-C.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['K'] = BsdDB(dir + '/definitions-cache-K.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['D'] = BsdDB(dir + '/definitions-cache-D.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        self.defs_cache['M'] = BsdDB(dir + '/definitions-cache-M.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)
        assert sorted(self.defs_cache.keys()) == sorted(lib.CACHED_DEFINITIONS_FAMILIES)
        self.refs = db_cls(dir + '/references.db', ro, RefList)
        self.docs = db_cls(dir + '/doccomments.db', ro, RefList)
        self.dtscomp = dtscomp
        if dtscomp:
            self.comps = db_cls(dir + '/compatibledts.db', ro, RefList)
            self.comps_docs = db_cls(dir + '/compatibledts_docs.db', ro, RefList)
            # Use a RefList in case there are multiple doc comments for an identifier

    def close(self):
        self.defs.close()
        self.defs_cache['C'].close()
        self.defs_cache['K'].close()
        self.defs_cache['D'].close()
        self.defs_cache['M'].close()
        self.refs.close()
        self.docs.close()
        if self.dtscomp:
            self.comps.close()
            self.comps_docs.close()

class BlobsDB:
    def __init__(self, dir, readonly=True, shared=False):
        if os.path.isdir(dir):
            self.dir = dir
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), dir)

        ro = readonly
        NOOP = lambda x: x

        self.vars = BsdDB(dir + '/variables.db', ro, lambda x: int(x.decode()), shared=shared)
            # Key-value store of basic information
        self.blob = CachedBsdDB(dir + '/blobs.db', ro, lambda x: int(x.decode()), cachesize=50000, simple=True)
            # Map hash to sequential integer serial number
        self.hash = BsdDB(dir + '/hashes.db', ro, lambda x: x, shared=shared, cachesize=CACHESIZE)
            # Map serial number back to hash
        self.file = BsdDB(dir + '/filenames.db', ro, lambda x: x.decode(), shared=shared, cachesize=CACHESIZE)
            # Map serial number to filename
        self.vers = BsdDB(dir + '/versions.db', ro, PathList, shared=shared, cachesize=CACHESIZE)
        self.todo = BsdDB(dir + '/todo.db', ro, NOOP, shared=shared, cachesize=CACHESIZE)

    def close(self):
        self.vars.close()
        self.blob.close()
        self.hash.close()
        self.file.close()
        self.vers.close()

