import logging
import os
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool, Pool
from typing import Tuple

from elixir.lib import script, scriptLines, getFileFamily, isIdent, getDataDir, compatibleFamily, compatibleMacro
from elixir.data import PathList, DefList, RefList, DB

from find_compatible_dts import FindCompatibleDTS

FileId = Tuple[bytes, bytes, bytes]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Holds databases and update changes that are not commited yet
class UpdatePartialState:
    def __init__(self, db, tag, blobs, idx_to_hash_and_filename, hash_to_idx):
        self.db = db
        self.tag = tag
        self.blobs = blobs
        self.idx_to_hash_and_filename = idx_to_hash_and_filename
        self.hash_to_idx = hash_to_idx
        self.def_idents = {}

    def get_idx_from_hash(self, hash):
        if hash in self.hash_to_idx:
            return self.hash_to_idx[hash]
        else:
            return self.db.blob.get(hash)

    # Add definitions to database
    def add_defs(self, defs):
        for ident, occ_list in defs.items():
            if self.db.defs.exists(ident):
                obj = self.db.defs.get(ident)
            else:
                obj = DefList()

            if ident in self.def_idents:
                lines_list = self.def_idents[ident]
            else:
                lines_list = []
                self.def_idents[ident] = lines_list

            for (idx, type, line, family) in occ_list:
                obj.append(idx, type, line, family)
                lines_list.append((idx, line))

            self.db.defs.put(ident, obj)

    # Add references to database
    def add_refs(self, refs):
        for ident, idx_to_lines in refs.items():
            deflist = self.def_idents.get(ident)
            if deflist is None:
                continue

            def deflist_exists(idx, n):
                for didx, dn in deflist:
                    if didx == idx and dn == n:
                        return True
                return False

            obj = self.db.refs.get(ident)
            if obj is None:
                obj = RefList()

            for (idx, family), lines in idx_to_lines.items():
                lines = [n for n in lines if not deflist_exists(str(idx).encode(), n)]

                if len(lines) != 0:
                    lines_str = ','.join((str(n) for n in lines))
                    obj.append(idx, lines_str, family)

            self.db.refs.put(ident, obj)

    # Add documentation references to database
    def add_docs(self, idx, family, docs):
        self.add_to_reflist(self.db.docs, idx, family, docs)

    # Add compatible references to database
    def add_comps(self, idx, family, comps):
        self.add_to_reflist(self.db.comps, idx, family, comps)

    # Add compatible docs to database
    def add_comps_docs(self, idx, family, comps_docs):
        comps_result = {}
        for ident, v in comps_docs.items():
            if self.db.comps.exists(ident):
                comps_result[ident] = v

        self.add_to_reflist(self.db.comps_docs, idx, family, comps_result)

    # Add data to database file that uses reflist schema
    def add_to_reflist(self, db_file, idx, family, to_add):
        for ident, lines in to_add.items():
            if db_file.exists(ident):
                obj = db_file.get(ident)
            else:
                obj = RefList()

            lines_str = ','.join((str(n) for n in lines))
            obj.append(idx, lines_str, family)
            db_file.put(ident, obj)

    def generate_defs_caches(self):
        for key in self.db.defs.get_keys():
            value = self.db.defs.get(key)
            for family in ['C', 'K', 'D', 'M']:
                if (compatibleFamily(value.get_families(), family) or
                            compatibleMacro(value.get_macros(), family)):
                    self.db.defs_cache[family].put(key, b'')


# NOTE: not thread safe, has to be ran before the actual job is started
# Builds UpdatePartialState
def build_partial_state(db: DB, tag: bytes):
    if db.vars.exists('numBlobs'):
        idx = db.vars.get('numBlobs')
    else:
        idx = 0

    # Get blob hashes and associated file names (without path)
    blobs = scriptLines('list-blobs', '-f', tag)

    idx_to_hash_and_filename = {}
    hash_to_idx = {}

    # Collect new blobs, assign database ids to the blobs
    for blob in blobs:
        hash, filename = blob.split(b' ',maxsplit=1)
        blob_exist = db.blob.exists(hash)
        if not blob_exist:
            hash_to_idx[hash] = idx
            idx_to_hash_and_filename[idx] = (hash, filename.decode())
            idx += 1

    # Reserve ids in blob space - if update is interrupted, as long as all database writes
    # finished correctly, the changes won't be seen by the application itself.
    # NOTE: this variable does not represent the actual number of blos in the database now,
    # just the number of ids reserved for blobs. the space is not guaranteed to be continous
    # if update job is interrupted or versions are scrubbed from the database.
    db.vars.put('numBlobs', idx)

    return UpdatePartialState(db, tag, blobs, idx_to_hash_and_filename, hash_to_idx)

# NOTE: not thread safe, has to be ran after job is finished
# Applies changes from partial update state - mainly to hash, file, blob and versions databases
# It is assumed that indexes not present in versions are ignored
def apply_partial_state(state: UpdatePartialState):
    for idx, (hash, filename) in state.idx_to_hash_and_filename.items():
        state.db.hash.put(idx, hash)
        state.db.file.put(idx, filename)

    for hash, idx in state.hash_to_idx.items():
        state.db.blob.put(hash, idx)

    # Update versions
    buf = []

    for blob in state.blobs:
        hash, path = blob.split(b' ', maxsplit=1)
        idx = state.get_idx_from_hash(hash)
        buf.append((idx, path))

    buf.sort()
    obj = PathList()
    for idx, path in buf:
        obj.append(idx, path)

    state.db.vers.put(state.tag, obj, sync=True)
    state.generate_defs_caches()


# Collect definitions from ctags for a file
def get_defs(file_id: FileId):
    idx, hash, filename = file_id
    defs = {}
    family = getFileFamily(filename)
    if family in [None, 'M']:
        return {}

    lines = scriptLines('parse-defs', hash, filename, family)

    for l in lines:
        ident, type, line = l.split(b' ')
        type = type.decode()
        line = int(line.decode())
        if isIdent(ident):
            if ident not in defs:
                defs[ident] = []
            defs[ident].append((idx, type, line, family))

    return defs

# Collect references from the tokenizer for a file
def get_refs(file_id: FileId):
    idx, hash, filename = file_id
    refs = {}
    family = getFileFamily(filename)
    if family is None:
        return

    # Kconfig values are saved as CONFIG_<value>
    prefix = b'' if family != 'K' else b'CONFIG_'

    tokens = scriptLines('tokenize-file', '-b', hash, family)
    even = True
    line_num = 1

    for tok in tokens:
        even = not even
        if even:
            tok = prefix + tok

            # We only index CONFIG_??? in makefiles
            if (family != 'M' or tok.startswith(b'CONFIG_')):
                if tok not in refs:
                    refs[tok] = {}

                if (idx, family) not in refs[tok]:
                    refs[tok][(idx, family)] = []

                refs[tok][(idx, family)].append(line_num)

        else:
            line_num += tok.count(b'\1')

    return refs

# Collect compatible script output into reflist-schema compatible format
def collect_get_blob_output(lines):
    results = {}
    for l in lines:
        ident, line = l.split(' ')
        line = int(line)

        if ident not in results:
            results[ident] = []
        results[ident].append(line)

    return results

# Collect docs from doc comments script for a single file
def get_docs(file_id: FileId):
    idx, hash, filename = file_id
    family = getFileFamily(filename)
    if family in [None, 'M']: return

    lines = (line.decode() for line in scriptLines('parse-docs', hash, filename))
    docs = collect_get_blob_output(lines)

    return (idx, family, docs)

# Collect compatible references for a single file
def get_comps(file_id: FileId):
    idx, hash, filename = file_id
    family = getFileFamily(filename)
    if family in [None, 'K', 'M']: return

    compatibles_parser = FindCompatibleDTS()
    lines = compatibles_parser.run(scriptLines('get-blob', hash), family)
    comps = collect_get_blob_output(lines)

    return (idx, family, comps)

# Collect compatible documentation references for a single file
def get_comps_docs(file_id: FileId):
    idx, hash, _ = file_id
    family = 'B'

    compatibles_parser = FindCompatibleDTS()
    lines = compatibles_parser.run(scriptLines('get-blob', hash), family)
    comps_docs = {}
    for l in lines:
        ident, line = l.split(' ')

        if ident not in comps_docs:
            comps_docs[ident] = []
        comps_docs[ident].append(int(line))

    return (idx, family, comps_docs)


# Update a single version - collects data from all the stages and saves it in the database
def update_version(db, tag, pool, dts_comp_support):
    state = build_partial_state(db, tag)

    # Collect blobs to process and split list of blobs into chunks
    idxes = [(idx, hash, filename) for (idx, (hash, filename)) in state.idx_to_hash_and_filename.items()]
    chunksize = int(len(idxes) / cpu_count())
    chunksize = min(max(1, chunksize), 100)

    for result in pool.imap_unordered(get_defs, idxes, chunksize):
        if result is not None:
            state.add_defs(result)

    logger.info("defs done")

    for result in pool.imap_unordered(get_docs, idxes, chunksize):
        if result is not None:
            state.add_docs(*result)

    logger.info("docs done")

    if dts_comp_support:
        for result in pool.imap_unordered(get_comps, idxes, chunksize):
            if result is not None:
                state.add_comps(*result)

        logger.info("dts comps done")

        for result in pool.imap_unordered(get_comps_docs, idxes, chunksize):
            if result is not None:
                state.add_comps_docs(*result)

        logger.info("dts comps docs done")

    for result in pool.imap_unordered(get_refs, idxes, chunksize):
        if result is not None:
            state.add_refs(result)

    logger.info("refs done")

    logger.info("update done, applying partial state")
    apply_partial_state(state)

if __name__ == "__main__":
    dts_comp_support = int(script('dts-comp'))
    db = None

    with Pool() as pool:
        for tag in scriptLines('list-tags'):
            if db is None:
                if "ELIXIR_CACHE" in os.environ:
                    db = DB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False, cachesize=(2,0))
                else:
                    db = DB(getDataDir(), readonly=False, dtscomp=dts_comp_support, shared=False)

            if not db.vers.exists(tag):
                logger.info("updating tag %s", tag)
                update_version(db, tag, pool, dts_comp_support)
                db.close()
                db = None

