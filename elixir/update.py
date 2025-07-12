import os.path
import logging
import time
import signal
import bisect
import math
import queue
import threading
import multiprocessing
from multiprocessing import cpu_count, set_start_method
from multiprocessing.pool import Pool
from typing import Dict, Iterable, List, Optional, Tuple, Set
from collections import OrderedDict

from find_compatible_dts import FindCompatibleDTS

from elixir.data import BlobsDB, BsdDB, CachedBsdDB, DefList, PathList, RefList, RelationsDB, defTypeD
from elixir.lib import (
    compatibleFamily,
    compatibleMacro,
    getDataDir,
    getFileFamily,
    isIdent,
    script,
    scriptLines,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# File identification - id, hash, filename
FileId = Tuple[int, bytes, str]

# Definitions parsing output, ident -> list of (file_idx, type, line, family)
DefsDict = Dict[bytes, List[Tuple[int, str, int, str]]]

# References parsing output, ident -> (file_idx, family) -> list of lines
RefsDict = Dict[bytes, Dict[Tuple[int, str], List[int]]]

# Generic dictionary of ident -> list of lines
LinesListDict = Dict[str, List[int]]

# File idx -> (hash, filename, is a new file?)
IdxCache = Dict[int, Tuple[bytes, str, bool]]

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

# Check if definition for ident is visible in current version
def def_in_version(def_ident: DefList, version_blobs: Set[int]) -> bool:
    def_ident.populate_entries()

    prev_idx = None
    for def_idx, _, _, _ in reversed(def_ident.entries):
        if def_idx == prev_idx:
            continue
        if def_idx in version_blobs:
            return True
        prev_idx = def_idx
    return False

# Add definitions to database
def add_defs(db: RelationsDB, defs):
    for ident, tmp_pack in defs:
        obj = db.defs.get(ident)
        if obj is None:
            obj = DefList()

        start = time.time()

        obj.add_tmp_pack(tmp_pack)

        db.defs.append_time += time.time()-start

        db.defs.put(ident, obj)


# Add references to database
def add_refs(db: RelationsDB, in_ver_cache: Cache, version_blobs: Set[int], refs):
    for ident, tmp_pack in refs:
        deflist = db.defs.get(ident)
        if deflist is None:
            continue

        if not in_ver_cache.contains(ident):
            in_version = def_in_version(deflist, version_blobs)
            if not in_version:
                in_ver_cache.put(ident, False)
                continue
            in_ver_cache.put(ident, True)
        elif not in_ver_cache.get(ident):
            continue

        obj = db.refs.get(ident)
        if obj is None:
            obj = RefList()

        obj.add_tmp_pack(tmp_pack)
        db.refs.put(ident, obj)

# Add documentation references to database
def add_docs(db: RelationsDB, docs):
    add_to_lineslist(db.docs, docs)

# Add compatible references to database
def add_comps(db: RelationsDB, comps):
    add_to_lineslist(db.comps, comps)

# Add compatible docs to database
def add_comps_docs(db: RelationsDB, comps_docs):
    add_to_lineslist(db.comps_docs, comps_docs)

# Add data to a database file that uses lines list schema
def add_to_lineslist(db_file: BsdDB, to_add: List[Tuple[str, bytes]]):
    for ident, tmp_pack in to_add:
        obj = db_file.get(ident)
        if obj is None:
            obj = RefList()

        obj.add_tmp_pack(tmp_pack)
        db_file.put(ident, obj)


# Adds blob list to database, returns blob id -> (hash, filename) dict
def collect_blobs(db: BlobsDB, tag: bytes) -> IdxCache:
    idx = db.vars.get('numBlobs')
    if idx is None:
        idx = 0

    # Get blob hashes and associated file names (without path)
    blobs = scriptLines('list-blobs', '-p', tag)
    versionBuf = []
    idx_to_hash_and_filename = {}

    to_blob = []
    to_hash = []
    to_file = []
    to_todo = []

    # Collect new blobs, assign database ids to the blobs
    for blob in blobs:
        hash, path = blob.split(b' ',maxsplit=1)
        filename = os.path.basename(path.decode())
        blob_idx = db.blob.get(hash)

        if blob_idx is not None:
            versionBuf.append((blob_idx, path))
            if blob_idx not in idx_to_hash_and_filename:
                idx_to_hash_and_filename[blob_idx] = (hash, filename, False)
        else:
            versionBuf.append((idx, path))
            idx_to_hash_and_filename[idx] = (hash, filename, True)
            to_blob.append((hash, idx))
            to_hash.append((str(idx), hash))
            to_file.append((str(idx), filename))
            to_todo.append((str(idx), hash))
            idx += 1

    to_blob.sort(key=lambda x: x[0])
    to_hash.sort(key=lambda x: x[0])
    to_file.sort(key=lambda x: x[0])
    to_todo.sort(key=lambda x: x[0])

    for k, v in to_blob: db.blob.put(k, v)
    for k, v in to_hash: db.hash.put(k, v)
    for k, v in to_file: db.file.put(k, v)
    for k, v in to_todo: db.todo.put(k, v)

    # Update number of blobs in the database
    db.vars.put('numBlobs', idx)

    # Add mapping blob id -> path to version database
    versionBuf.sort()
    obj = PathList()
    for i, path in versionBuf:
        obj.append(i, path)
    db.vers.put(tag, obj, sync=True)

    return idx_to_hash_and_filename

# Generate definitions cache databases
def generate_defs_caches(db: RelationsDB):
    for key in db.defs.get_keys():
        value = db.defs.get(key)
        for family in ['C', 'K', 'D', 'M']:
            if (compatibleFamily(value.get_families(), family) or
                        compatibleMacro(value.get_macros(), family)):
                db.defs_cache[family].put(key, b'')


# Collect definitions from ctags for a file
def get_defs(file_id: FileId) -> Optional[List[Tuple[str, bytes]]]:
    idx, file_hash, filename = file_id
    defs = {}
    family = getFileFamily(filename)
    if family in (None, 'M'):
        return None

    lines = scriptLines('parse-defs', file_hash, filename, family)

    for l in lines:
        ident, type, line = l.split(b' ')
        t = type.decode()
        line = int(line.decode())
        if isIdent(ident):
            if t not in defTypeD:
                continue
            if ident not in defs:
                defs[ident] = DefList()
            defs[ident].append(idx, t, line, family)

    result = [(k, v.tmp_pack()) for k, v in defs.items()]
    result.sort(key=lambda x: x[0])
    return result

# Collect references from the tokenizer for a file
def get_refs(file_id: FileId, defs: CachedBsdDB) -> Optional[List[Tuple[str, bytes]]]:
    idx, file_hash, filename = file_id
    refs = {}
    family = getFileFamily(filename)
    if family is None:
        return

    # Kconfig values are saved as CONFIG_<value>
    prefix = b'' if family != 'K' else b'CONFIG_'

    tokens = scriptLines('tokenize-file', '-b', file_hash, family)
    even = True
    line_num = 1

    def deflist_exists(deflist, idx: int, line: int):
        deflist.populate_entries()
        start = bisect.bisect_left(deflist.entries, idx, key=lambda x: x[0])

        for def_idx, _, def_line, _ in deflist.entries[start:]:
            if def_idx == idx:
                if def_line == line:
                    return True
            else:
                break

        return False

    for tok in tokens:
        even = not even
        if even:
            tok = prefix + tok

            # We only index CONFIG_??? in makefiles
            if (family != 'M' or tok.startswith(b'CONFIG_')):
                deflist = defs.get(tok)
                if not deflist:
                    continue

                if deflist_exists(deflist, idx, line_num):
                    continue

                if tok not in refs:
                    refs[tok] = {}

                if (idx, family) not in refs[tok]:
                    refs[tok][(idx, family)] = [str(line_num)]
                else:
                    refs[tok][(idx, family)].append(str(line_num))

        else:
            line_num += tok.count(b'\1')

    result = []
    for k, v in refs.items():
        obj = RefList()
        for (idx, family), lines in v.items():
            obj.append(idx, ','.join(lines), family)
        result.append((k, obj.pack_tmp()))

    result.sort(key=lambda x: x[0])
    return result

# Collect compatible script output into lineslinst-schema compatible format
def collect_get_blob_output(idx: int, lines: Iterable[str], family: str) -> List[Tuple[str, bytes]]:
    results = {}
    for l in lines:
        ident, line = l.split(' ')

        if ident not in results:
            results[ident] = []
        results[ident].append(line)

    final_results = []
    for k, lines in results.items():
        obj = RefList()
        obj.append(idx, ','.join(lines), family)
        final_results.append((k, obj.pack_tmp()))

    final_results.sort(key=lambda x: x[0])

    return final_results

# Collect docs from doc comments script for a single file
def get_docs(file_id: FileId) -> Optional[List[Tuple[str, bytes]]]:
    idx, file_hash, filename = file_id
    family = getFileFamily(filename)
    if family in (None, 'M'): return

    start = time.time()
    lines = (line.decode() for line in scriptLines('parse-docs', file_hash, filename))
    parser_time = time.time()-start

    if parser_time > 10:
        logger.info("docs timeout %d %d", parser_time, file_id)

    return collect_get_blob_output(idx, lines, family)

# Collect compatible references for a single file
def get_comps(file_id: FileId) -> Optional[List[Tuple[str, bytes]]]:
    idx, file_hash, filename = file_id
    family = getFileFamily(filename)
    if family in (None, 'K', 'M'): return

    compatibles_parser = FindCompatibleDTS()

    start = time.time()
    lines = compatibles_parser.run(scriptLines('get-blob', file_hash), family)
    parser_time = time.time()-start

    if parser_time > 10:
        logger.info("comps docs timeout %d %d", parser_time, file_id)

    return collect_get_blob_output(idx, lines, family)

# Collect compatible documentation references for a single file
def get_comps_docs(file_id: FileId, comps_db: CachedBsdDB) -> List[Tuple[str, bytes]]:
    idx, file_hash, _ = file_id
    family = 'B'

    compatibles_parser = FindCompatibleDTS()
    lines = compatibles_parser.run(scriptLines('get-blob', file_hash), family)
    comps_docs = {}
    for l in lines:
        ident, line = l.split(' ')
        if not comps_db.exists(ident):
            continue
        if ident not in comps_docs:
            comps_docs[ident] = []
        comps_docs[ident].append(line)

    final_results = []
    for k, lines in comps_docs.items():
        obj = RefList()
        obj.append(idx, ','.join(lines), family)
        final_results.append((k, obj.pack_tmp()))

    final_results.sort(key=lambda x: x[0])

    return final_results


def call_stage_1(args):
    return stage_1(*args)

def stage_1(file_id: FileId, dts_comp_support: bool):
    result = {
        "defs": get_defs(file_id),
        "docs": get_docs(file_id),
    }

    if dts_comp_support:
        result["dts_comps"] = get_comps(file_id)

    return result

def call_stage_2(args):
    blobs, tag, dts_comp_support = args
    defs = CachedBsdDB(getDataDir() + '/definitions.db', True, DefList, 1000)
    if dts_comp_support:
        comps = CachedBsdDB(getDataDir() + '/compatibledts.db', True, DefList, 1000)
    else:
        comps = None

    result = {
        "tag": tag,
        "refs": [],
    }

    for blob in blobs:
        tmp = stage_2(blob, defs, comps, dts_comp_support)

        if tmp["refs"] is not None:
            result["refs"].extend(tmp["refs"])

        if dts_comp_support and tmp["dts_comps_docs"] is not None:
            result["dts_comps_docs"].extend(tmp["dts_comps_docs"])

    return result

def stage_2(file_id: FileId, defs: CachedBsdDB, comps: CachedBsdDB, dts_comp_support: bool):
    result = {
        "refs": get_refs(file_id, defs),
    }
    if dts_comp_support:
        result["dts_comps_docs"] = get_comps_docs(file_id, comps)
    return result

def generate_blobs(queue: queue.Queue, tags, dts_comp_support: bool):
    db = BlobsDB(getDataDir(), readonly=False, shared=False)
    for tag in tags:
        if sigint_caught:
            break

        if db.vers.exists(tag):
            continue

        start = time.time()
        idx_to_hash_and_filename = collect_blobs(db, tag)

        new_blobs = [
            ((idx, file_hash, filename), dts_comp_support)
            for (idx, (file_hash, filename, new))
            in idx_to_hash_and_filename.items() if new
        ]
        end = time.time()

        logger.info("updating tag %s with %d new blobs, collect took %d", tag, len(new_blobs), end-start)
        queue.put({"blobs": new_blobs})

    queue.put({"quit": True})
    db.close()
    logger.info("blobs thread quit")

def yield_blobs(tags, dts_comp_support: bool):
    blobs_queue = multiprocessing.Queue(maxsize=cpu_count())
    generate_blobs_thread = multiprocessing.Process(target=generate_blobs, name="blobs_process", args=(blobs_queue, tags, dts_comp_support))
    generate_blobs_thread.start()

    while True:
        item = blobs_queue.get()
        if "quit" in item:
            break

        yield from item["blobs"]

    generate_blobs_thread.join()
    logger.info("yield blob quit")

def split_into_chunks(list, chunk_size):
    return (list[i:i+chunk_size] for i in range(0, len(list), chunk_size))

def generate_stage_2_blobs(queue: queue.Queue, tags, dts_comp_support: bool):
    todo_db = BsdDB(getDataDir() + '/todo.db', False, lambda x: x, shared=False)
    vers_db = BsdDB(getDataDir() + '/versions.db', True, PathList, shared=False)

    for tag in tags:
        if sigint_caught:
            break

        vers = vers_db.get(tag)
        if vers is None:
            logger.warning("tag %s not in vers", tag)
            continue

        logger.info("updating refs of tag %s", tag)

        idxes = []
        for idx, path in vers.iter():
            file_hash = todo_db.get(idx)
            if file_hash is not None:
                todo_db.delete(idx)
                idxes.append((idx, file_hash, os.path.basename(path)))

        for chunk in split_into_chunks(idxes, math.ceil(len(idxes)/cpu_count())):
            queue.put({"blobs": (chunk, tag.decode(), dts_comp_support)})

    queue.put({"quit": True})
    todo_db.close()
    vers_db.close()
    logger.info("blobs2 thread quit")

def yield_stage_2_blobs(tags, dts_comp_support: bool):
    blobs_queue = multiprocessing.Queue(maxsize=cpu_count())
    generate_blobs_thread = multiprocessing.Process(target=generate_stage_2_blobs, name="blobs2_process", args=(blobs_queue, tags, dts_comp_support))
    generate_blobs_thread.start()

    while True:
        item = blobs_queue.get()
        if "quit" in item:
            break

        yield item["blobs"]

    logger.info("yield blob quit")
    generate_blobs_thread.join()

def db_defs_thread(defs_queue: multiprocessing.Queue):
    dts_comp_support = bool(int(script('dts-comp')))
    db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=50000)
    processed = 0
    total_processing_time = 0

    while True:
        result = defs_queue.get()
        if "quit" in result:
            break

        start_defs = time.time()

        if result["defs"] is not None:
            add_defs(db, result["defs"])

        start_docs = time.time()

        if result["docs"] is not None:
            add_docs(db, result["docs"])

        start_dts = time.time()

        if "dts_comps" in result and result["dts_comps"] is not None:
            add_comps(db, result["dts_comps"])

        end = time.time()

        processed += 1
        total_processing_time += end-start_defs

        if end-start_defs > 1:
            logger.info("processing result took %d %d %d %d %d", time.time(),
              len(result["defs"]) if "defs" in result and result["defs"] is not None else 0,
              start_docs-start_defs, start_dts-start_dts, end-start_dts)

        if processed % 1000 == 0:
            logger.info("total defs stats %f %f", processed, total_processing_time)
            logger.info("defs stats %f %f %f %f %f", db.defs.raw_put_time, db.defs.raw_get_time,
                  db.defs.raw_put_convert_time, db.defs.raw_get_convert_time, db.defs.append_time)

    logger.info("quitting defs thread")
    db.close()

def db_refs_thread(refs_queue: queue.Queue):
    dts_comp_support = bool(int(script('dts-comp')))
    db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=50000)
    vers_db = BsdDB(getDataDir() + '/versions.db', True, PathList, shared=False)

    db.defs.close()
    db.defs.readonly = True
    db.defs.open()
    if dts_comp_support:
        db.comps.close()
        db.comps.readonly = True
        db.comps.open()

    in_def_cache = Cache(10000)
    vers_cache = Cache(cpu_count())

    while True:
        result = refs_queue.get()
        if "quit" in result:
            break

        tag = result["tag"]
        vers = vers_cache.get(tag)
        if vers is None:
            vers = set()
            pathlist = vers_db.get(tag)
            for idx, _ in pathlist.iter():
                vers.add(idx)
            vers_cache.put(tag, vers)

        if "dts_comps_docs" in result and result["dts_comps_docs"] is not None:
            add_comps_docs(db, result["dts_comps_docs"])

        if result["refs"] is not None:
            add_refs(db, in_def_cache, vers, result["refs"])

        refs_queue.task_done()

    logger.info("quitting refs thread")
    db.close()

def update(pool):
    dts_comp_support = bool(int(script('dts-comp')))
    tags = scriptLines('list-tags')

    defs_queue = multiprocessing.Queue(maxsize=cpu_count())
    defs_thread = multiprocessing.Process(target=db_defs_thread, args=(defs_queue,), name="defs_process")
    defs_thread.start()

    i = 0
    for result in pool.imap_unordered(call_stage_1, yield_blobs(tags, dts_comp_support)):
        i += 1
        defs_queue.put(result)
        if i % 1000 == 0:
            logger.info("defs queue len %d", defs_queue.qsize())

    defs_queue.put({"quit": True})
    defs_thread.join()

    logger.info("processing refs")

    refs_queue = queue.Queue(maxsize=cpu_count())
    refs_thread = threading.Thread(target=db_refs_thread, args=(refs_queue,))
    refs_thread.start()

    for result in pool.imap_unordered(call_stage_2, yield_stage_2_blobs(tags, dts_comp_support)):
        i += 1
        refs_queue.put(result)
        if refs_queue.qsize() % 1000 == 0:
            logger.info("refs queue len %d", refs_queue.qsize())

    refs_queue.join()
    refs_queue.put({"quit": True})
    refs_thread.join()

sigint_caught = False

def sigint_handler(signum, _frame):
    global sigint_caught
    if not sigint_caught:
        logger.info("Caught SIGINT... the script will exit after processing this version")
        signal.signal(signum, signal.SIG_IGN)
        sigint_caught = True

signal.signal(signal.SIGINT, sigint_handler)

def ignore_sigint():
    signal.signal(signal.SIGINT, lambda _,__: None)

if __name__ == "__main__":
    dts_comp_support = bool(int(script('dts-comp')))
    set_start_method('spawn')
    with Pool(initializer=ignore_sigint) as pool:
        update(pool)

    db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=100000)
    logger.info("generating def caches")
    generate_defs_caches(db)
    logger.info("def caches generated")
    db.close()
    logger.info("database closed")


