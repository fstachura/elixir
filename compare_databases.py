import sys
import os.path
import berkeleydb
import difflib
from collections import OrderedDict
from elixir.data import DB, DefList, RefList, PathList

class Cache:
    def __init__(self, size):
        self.cache = OrderedDict()
        self.size = size

    def contains(self, key):
        return key in self.cache

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key, val):
        self.cache[key] = val
        self.cache.move_to_end(key)
        if len(self.cache) > self.size:
            self.cache.popitem(last=False)

def create_compare_deflist(get_hash):
    def compare_deflist(key, val_a, val_b):
        if val_a == val_b:
            return

        val_a = DefList(val_a)
        val_b = DefList(val_b)

        key_printed = False
        a_lines = list(f"{get_hash(False, id)}:{type}:{line}:{family}" for (id, type, line, family) in val_a.iter())
        b_lines = list(f"{get_hash(True, id)}:{type}:{line}:{family}" for (id, type, line, family) in val_b.iter())
        for d in difflib.unified_diff(a_lines, b_lines, n=0):
            if d[0] in '+-' and not d.startswith('+++') and not d.startswith('---'):
                if not key_printed:
                    print("?", key.decode())
                    key_printed = True
                print(d)

    return compare_deflist

def create_compare_reflist(get_hash):
    def compare_reflist(key, val_a, val_b):
        if val_a == val_b:
            return

        val_a = RefList(val_a)
        val_b = RefList(val_b)

        key_printed = False
        a_lines = list(f"{get_hash(False, id)}:{lines}:{family}" for (id, lines, family) in val_a.iter())
        b_lines = list(f"{get_hash(True, id)}:{lines}:{family}" for (id, lines, family) in val_b.iter())
        for d in difflib.unified_diff(a_lines, b_lines, n=0):
            if d[0] in '+-' and not d.startswith('+++') and not d.startswith('---'):
                if not key_printed:
                    print("?", key.decode())
                    key_printed = True
                print(d)

    return compare_reflist

def compare_db(db_a, db_b, compare_keys):
    cur_a, cur_b = db_a.cursor(), db_b.cursor()

    key_a, val_a = cur_a.get(berkeleydb.db.DB_FIRST) or (None, None)
    key_b, val_b = cur_b.get(berkeleydb.db.DB_FIRST) or (None, None)
    while key_a is not None or key_b is not None:
        if key_a == key_b:
            compare_keys(key_a, val_a, val_b)
            key_a, val_a = cur_a.next() or (None, None)
            key_b, val_b = cur_b.next() or (None, None)
        elif key_a is None or key_a > key_b:
            print("+", key_b.decode())
            assert db_a.get(key_b) is None
            key_b, val_b = cur_b.next() or (None, None)
        elif key_b is None or key_a < key_b:
            print("-", key_a.decode())
            assert db_b.get(key_a) is None
            key_a, val_a = cur_a.next() or (None, None)
        else:
            break

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage", sys.argv[0], "data_dir_a", "data_dir_b")
        exit(1)

    db_a, db_b = DB(sys.argv[1], True), DB(sys.argv[2], True)

    hash_cache = Cache(10000)
    def get_hash(is_b, key):
        if result := hash_cache.get((is_b, key)):
            return result

        if not is_b:
            val = db_a.hash.get(key)
        else:
            val = db_b.hash.get(key)

        if val is None:
            return None

        hash_cache.put((is_b, key), val.decode())
        return val.decode()

    print("================= DEFS =================")
    compare_db(db_a.defs.db, db_b.defs.db, create_compare_deflist(get_hash))
    print("================= REFS =================")
    compare_db(db_a.refs.db, db_b.refs.db, create_compare_reflist(get_hash))
    print("================= DOCS =================")
    compare_db(db_a.docs.db, db_b.docs.db, create_compare_reflist(get_hash))
    if os.path.exists(os.path.join(sys.argv[1], '/compatibledts.db')):
        print("================= COMPS =================")
        compare_db(db_a.comps.db, db_b.comps.db, create_compare_reflist(get_hash))
        print("================= COMPS DOCS =================")
        compare_db(db_a.comps_docs.db, db_b.comps_docs.db, create_compare_reflist(get_hash))

