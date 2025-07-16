from multiprocessing import process
import os.path
import logging
import time
import signal
import bisect
import math
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
    scriptLinesGen,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(process)d %(levelname)s: %(message)s')
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
def add_refs(db: RelationsDB, refs):
    for ident, tmp_pack in refs:
        deflist = db.defs.get(ident)
        if deflist is None:
            continue

        obj = db.refs.get(ident)
        if obj is None:
            obj = RefList()

        start = time.time()

        obj.add_tmp_pack(tmp_pack)

        db.refs.append_time += time.time()-start

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
def get_refs(file_id: FileId, defs: CachedBsdDB, blobs_in_vers: Set[int]) -> Optional[List[Tuple[str, bytes]]]:
    idx, file_hash, filename = file_id
    refs = {}
    family = getFileFamily(filename)
    if family is None:
        return

    # Kconfig values are saved as CONFIG_<value>
    prefix = b'' if family != 'K' else b'CONFIG_'

    tokens = scriptLinesGen('tokenize-file', '-b', file_hash, family)
    even = True
    line_num = 1

    in_ver_cache = Cache(10000)

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

                if not in_ver_cache.contains(tok):
                    in_version = def_in_version(deflist, blobs_in_vers)
                    if not in_version:
                        in_ver_cache.put(tok, False)
                        continue
                    in_ver_cache.put(tok, True)
                elif not in_ver_cache.get(tok):
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
    lines = compatibles_parser.run(scriptLinesGen('get-blob', file_hash), family)
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


def generate_stage_1_blobs(blobs_queue: multiprocessing.Queue, tags):
    logger.info("stage 1 blobs thread start")

    db = BlobsDB(getDataDir(), readonly=False, shared=False)
    for tag in tags:
        if sigint_caught:
            break

        if db.vers.exists(tag):
            continue

        start = time.time()
        idx_to_hash_and_filename = collect_blobs(db, tag)


        new_blobs = [
            (idx, file_hash, filename)
            for (idx, (file_hash, filename, new))
            in idx_to_hash_and_filename.items() if new
        ]
        end = time.time()

        logger.info("updating tag %s with %d new blobs, collect took %d", tag, len(new_blobs), end-start)
        for chunk in split_into_chunks(new_blobs, math.ceil(len(new_blobs)/(cpu_count()*8))):
            blobs_queue.put({"blobs": chunk})

    db.close()

    logger.info("stage 1 blobs thread quit")

def process_stage_1_blobs(blobs_queue: multiprocessing.Queue, results_queue: multiprocessing.Queue):
    logging.info("stage 1 process thread start")
    dts_comp_support = bool(int(script('dts-comp')))

    while True:
        args = blobs_queue.get()
        if "quit" in args:
            break

        result = {
            "defs": [],
            "docs": [],
        }

        if dts_comp_support:
            result["dts_comps"] = []

        for blob in args["blobs"]:
            try:
                if defs := get_defs(blob):
                    result["defs"].extend(defs)
            except Exception:
                logger.exception("failed to process defs for %s", blob)

            try:
                if docs := get_docs(blob):
                    result["docs"].extend(docs)
            except Exception:
                logger.exception("failed to process docs for %s", blob)

            if dts_comp_support:
                try:
                    if dts_comps := get_comps(blob):
                        result["dts_comps"].extend(dts_comps)
                except Exception:
                    logger.exception("failed to process dts comps for %s", blob)

        results_queue.put(result)

    logging.info("stage 1 process thread quit")

def put_stage_1_results(defs_queue: multiprocessing.Queue):
    logging.info("stage 1 put thread start")

    dts_comp_support = bool(int(script('dts-comp')))
    db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=10000)
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
            logger.info("processing result took %d %d %d %d", 
              len(result["defs"]) if "defs" in result and result["defs"] is not None else 0,
              start_docs-start_defs, start_dts-start_dts, end-start_dts)

        if processed % 1000 == 0:
            logger.info("total defs stats %f %f", processed, total_processing_time)
            logger.info("defs stats %f %f %f %f %f", db.defs.raw_put_time, db.defs.raw_get_time,
                  db.defs.raw_put_convert_time, db.defs.raw_get_convert_time, db.defs.append_time)

    db.close()

    logger.info("stage 1 put thread quit")

def update_stage_1(tags):
    logger.info("stage 1 update start")

    db_blobs_queue = multiprocessing.Queue(maxsize=4*cpu_count())
    db_blobs_thread = multiprocessing.Process(target=generate_stage_1_blobs, args=(db_blobs_queue, tags))
    db_blobs_thread.start()

    results_queue = multiprocessing.Queue(maxsize=4*cpu_count())
    results_thread = multiprocessing.Process(target=put_stage_1_results, args=(results_queue,))
    results_thread.start()

    processing_threads = []
    for _ in range(cpu_count()):
        process = multiprocessing.Process(target=process_stage_1_blobs, args=(db_blobs_queue, results_queue))
        processing_threads.append(process)
        process.start()

    db_blobs_thread.join()

    for _ in range(len(processing_threads)):
        db_blobs_queue.put({"quit": True})

    for p in processing_threads:
        p.join()
        logger.info("process joined %s", str(p))

    results_queue.put({"quit": True})
    results_thread.join()

    logger.info("stage 1 update quit")


def split_into_chunks(list, chunk_size):
    return (list[i:i+chunk_size] for i in range(0, len(list), chunk_size))

def generate_stage_2_blobs(queue: multiprocessing.Queue, tags):
    logger.info("stage 2 blob thread start")

    todo_db = BsdDB(getDataDir() + '/todo.db', False, lambda x: x, shared=False, cachesize=(2,0))
    vers_db = BsdDB(getDataDir() + '/versions.db', True, PathList, shared=False, cachesize=(2,0))

    for tag in tags:
        if sigint_caught:
            break

        vers = vers_db.get(tag)
        if vers is None:
            logger.warning("tag %s not in vers", tag)
            continue

        idxes = []
        for idx, path in vers.iter():
            file_hash = todo_db.get(idx)
            if file_hash is not None:
                todo_db.delete(idx)
                idxes.append((idx, file_hash, os.path.basename(path)))

        if len(idxes) == 0:
            continue

        logger.info("updating refs of tag %s blobs %d", tag, len(idxes))

        for chunk in split_into_chunks(idxes, math.ceil(len(idxes)/(cpu_count()*8))):
            queue.put({"blobs": (chunk, tag.decode())})

    todo_db.close()
    vers_db.close()

    logger.info("stage 2 blob thread quit")

def process_stage_2_blobs(blobs_queue: multiprocessing.Queue, results_queue: multiprocessing.Queue):
    logger.info("stage 2 process thread start")

    dts_comp_support = bool(int(script('dts-comp')))

    defs = CachedBsdDB(getDataDir() + '/definitions.db', True, DefList, 10000)
    if dts_comp_support:
        comps = CachedBsdDB(getDataDir() + '/compatibledts.db', True, DefList, 10000)
    else:
        comps = None

    vers_db = CachedBsdDB(getDataDir() + '/versions.db', True, PathList, cpu_count())

    while True:
        args = blobs_queue.get()
        if "quit" in args:
            break

        blobs, tag = args["blobs"]

        vers = set()
        pathlist = vers_db.get(tag)
        for idx, _ in pathlist.iter():
            vers.add(idx)

        result = {
            "tag": tag,
            "refs": [],
        }

        if dts_comp_support:
            result["dts_comps_docs"] = []

        for blob in blobs:
            try:
                if refs := get_refs(blob, defs, vers):
                    result["refs"].extend(refs)
            except Exception:
                logger.exception("failed to process refs for %s", blob)

            if dts_comp_support:
                try:
                    if comps_docs := get_comps_docs(blob, comps):
                        result["dts_comps_docs"].extend(comps_docs)
                except Exception:
                    logger.exception("failed to process dts comps docs for %s", blob)

        results_queue.put(result)

    logger.info("stage 2 process thread quit")

def put_stage_2_results(refs_queue: multiprocessing.Queue):
    logger.info("stage 2 put thread start")

    dts_comp_support = bool(int(script('dts-comp')))
    db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=10000)

    db.defs.close()
    db.defs.readonly = True
    db.defs.open()
    if dts_comp_support:
        db.comps.close()
        db.comps.readonly = True
        db.comps.open()

    processed = 0
    total_processing_time = 0

    while True:
        result = refs_queue.get()
        if "quit" in result:
            break

        start_tag = time.time()

        start_dts_comps_docs = time.time()

        if "dts_comps_docs" in result and result["dts_comps_docs"] is not None:
            add_comps_docs(db, result["dts_comps_docs"])

        start_refs = time.time()

        if result["refs"] is not None:
            add_refs(db, result["refs"])

        end = time.time()

        processed += 1
        total_processing_time += end-start_tag

        if end-start_tag > 1:
            logger.info("processing result took %d %f %f %f",
              len(result["refs"]) if "refs" in result and result["refs"] is not None else 0,
              start_dts_comps_docs-start_tag, start_refs-start_dts_comps_docs, end-start_refs)

        if processed % 50 == 0:
            logger.info("total refs stats %f %f", processed, total_processing_time)
            logger.info("refs stats %f %f %f %f %f", db.refs.raw_put_time, db.refs.raw_get_time,
                  db.refs.raw_put_convert_time, db.refs.raw_get_convert_time, db.refs.append_time)

    db.close()

    logger.info("stage 2 put thread quit")

def update_stage_2(tags):
    logger.info("stage 2 update start")

    db_blobs_queue = multiprocessing.Queue(maxsize=4*cpu_count())
    db_blobs_thread = multiprocessing.Process(target=generate_stage_2_blobs, args=(db_blobs_queue, tags))
    db_blobs_thread.start()

    db_put_queue = multiprocessing.Queue(maxsize=4*cpu_count())
    db_put_thread = multiprocessing.Process(target=put_stage_2_results, args=(db_put_queue,))
    db_put_thread.start()

    processing_threads = []
    for _ in range(cpu_count()):
        process = multiprocessing.Process(target=process_stage_2_blobs, args=(db_blobs_queue, db_put_queue))
        process.start()
        processing_threads.append(process)

    db_blobs_thread.join()
    logger.info("blobs thread joined")

    for _ in range(len(processing_threads)):
        db_blobs_queue.put({"quit": True})

    for p in processing_threads:
        p.join()
        logger.info("process joined %s", str(p))

    db_put_queue.put({"quit": True})
    db_put_thread.join()

    logger.info("stage 2 update quit")

def update():
    tags = list(reversed(scriptLines('list-tags')))[:3]
    update_stage_1(tags)
    if sigint_caught:
        return
    update_stage_2(tags)

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
    logging.info("starting update job")

    dts_comp_support = bool(int(script('dts-comp')))
    set_start_method('spawn')
    update()

    #db = RelationsDB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, update_cache=100000)
    logger.info("generating def caches")
    #generate_defs_caches(db)
    logger.info("def caches generated")
    #db.close()
    logger.info("database closed")


