import logging
import duckdb
import pandas
from multiprocessing import cpu_count
from multiprocessing.pool import Pool
from typing import Dict, Tuple, Iterable, List, Optional

from elixir.lib import script, scriptLines, getFileFamily, isIdent, getDataDir, compatibleFamily, compatibleMacro
from elixir.data import PathList, DefList, RefList, DB, BsdDB

from find_compatible_dts import FindCompatibleDTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# File identification - id, hash, filename
FileId = Tuple[int, bytes, str]

# Definitions parsing output, ident -> list of (file_idx, type, line, family)
DefsDict = Dict[bytes, List[Tuple[int, str, int, str]]]

# References parsing output, ident -> (file_idx, family) -> list of lines
RefsDict = Dict[bytes, Dict[Tuple[int, str], List[int]]]

# Cache of definitions found in current tag, ident -> list of (file_idx, line)
DefCache = Dict[bytes, List[Tuple[int, int]]]

# Generic dictionary of ident -> list of lines
LinesListDict = Dict[str, List[int]]

# Add definitions to database
def add_defs(db: DB, def_cache: DefCache, defs_df: DefsDict):
    db.sql("insert into defs (ident, file_id, type, line, family) select * from defs_df")
    #for ident, occ_list in defs.items():
    #    if ident in def_cache:
    #        lines_list = def_cache[ident]
    #    else:
    #        lines_list = []
    #        def_cache[ident] = lines_list

    #    for (idx, type, line, family) in occ_list:
    #        db.execute("insert into defs (ident, file_id, type, line, family) values select * from defs").fetchone()
    #        lines_list.append((idx, line))

# Add references to database
def add_refs(db: DB, def_cache: DefCache, refs_df: RefsDict):
    db.sql("insert into refs (ident, file_id, line, family) select * from refs_df where CAST(refs_df.ident as VARCHAR) in (select ident from defs)")
    #for ident, idx_to_lines in refs.items():
    #    # Skip reference if definition was not collected in this tag
    #    deflist = def_cache.get(ident)
    #    if deflist is None:
    #        continue

    #    def deflist_exists(idx, n):
    #        for didx, dn in deflist:
    #            if didx == idx and dn == n:
    #                return True
    #        return False

    #    for (idx, family), lines in idx_to_lines.items():
    #        lines = [n for n in lines if not deflist_exists(str(idx).encode(), n)]
    #        for line in lines:
    #            db.execute("insert into refs (ident, file_id, line, family) values select * from ref").fetchone()
    #                       [ident, idx, line, family]).fetchone()

# Add documentation references to database
def add_docs(db: DB, idx: int, family: str, docs: Dict[str, List[int]]):
    add_to_lineslist("docs", idx, family, docs)

# Add compatible references to database
def add_comps(db: DB, idx: int, family: str, comps: Dict[str, List[int]]):
    add_to_lineslist("comps", idx, family, comps)

# Add compatible docs to database
def add_comps_docs(db: DB, idx: int, family: str, comps_docs: Dict[str, List[int]]):
    comps_result = {}
    for ident, v in comps_docs.items():
        if db.comps.exists(ident):
            comps_result[ident] = v

    add_to_lineslist("comps_docs", idx, family, comps_result)

# Add data to a database file that uses lines list schema
def add_to_lineslist(db_file: BsdDB, idx: int, family: str, to_add: Dict[str, List[int]]):
    for ident, lines in to_add.items():
        for line in lines:
            db.execute("insert into " + db_file + " (ident, file_id, line, family) values (?, ?, ?, ?)",
                       [ident, idx, line, family]).fetchone()


# Adds blob list to database, returns blob id -> (hash, filename) dict
def collect_blobs(db: DB, tag: bytes) -> Dict[int, Tuple[bytes, str]]:
    # Get blob hashes and associated file names (without path)
    blobs = scriptLines('list-blobs', '-f', tag)
    blobs_dict = {"hash": [], "path": []}
    idx_to_hash_and_filename = {}

    # Collect new blobs, assign database ids to the blobs
    for blob in blobs:
        hash, filename = blob.split(b' ',maxsplit=1)
        blobs_dict["hash"].append(hash)
        blobs_dict["path"].append(filename)

    blobs_df = pandas.DataFrame.from_dict(blobs_dict)

    db.execute("insert into file (hash, path) select * from blobs_df where cast(blobs_df.hash as varchar) not in (select hash from file)").fetchone()

    result = db.sql("select file.id, file.hash, file.path from file join blobs_df on file.hash = blobs_df.hash").fetchall()
    for idx, hash, filename in result:
        idx_to_hash_and_filename[idx] = (hash, filename)

    result = db.execute("insert into versions (version, file_id) select ?, file.id from file join blobs_df on file.hash = blobs_df.hash", [tag]).fetchall()

    return idx_to_hash_and_filename

# Collect definitions from ctags for a file
def get_defs(file_id: FileId) -> Optional[DefsDict]:
    idx, hash, filename = file_id
    defs = {"ident": [], "file_id": [], "type": [], "line": [], "family": []}
    family = getFileFamily(filename)
    if family in (None, 'M'):
        return None

    lines = scriptLines('parse-defs', hash, filename, family)

    for l in lines:
        ident, type, line = l.split(b' ')
        type = type.decode()
        line = int(line.decode())
        if isIdent(ident):
            defs["ident"].append(ident)
            defs["file_id"].append(idx)
            defs["type"].append(type)
            defs["line"].append(line)
            defs["family"].append(family)

    return pandas.DataFrame.from_dict(defs)

# Collect references from the tokenizer for a file
def get_refs(file_id: FileId) -> Optional[RefsDict]:
    idx, hash, filename = file_id
    refs = {"ident": [], "file_id": [], "line": [], "family": []}
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
                refs["ident"].append(tok)
                refs["file_id"].append(idx)
                refs["line"].append(line_num)
                refs["family"].append(family)

        else:
            line_num += tok.count(b'\1')

    return pandas.DataFrame.from_dict(refs)

# Collect compatible script output into lineslinst-schema compatible format
def collect_get_blob_output(lines: Iterable[str]) -> LinesListDict:
    results = {}
    for l in lines:
        ident, line = l.split(' ')
        line = int(line)

        if ident not in results:
            results[ident] = []
        results[ident].append(line)

    return results

# Collect docs from doc comments script for a single file
def get_docs(file_id: FileId) -> Optional[Tuple[int, str, LinesListDict]]:
    idx, hash, filename = file_id
    family = getFileFamily(filename)
    if family in (None, 'M'): return

    lines = (line.decode() for line in scriptLines('parse-docs', hash, filename))
    docs = collect_get_blob_output(lines)

    return (idx, family, docs)

# Collect compatible references for a single file
def get_comps(file_id: FileId) -> Optional[Tuple[int, str, LinesListDict]]:
    idx, hash, filename = file_id
    family = getFileFamily(filename)
    if family in (None, 'K', 'M'): return

    compatibles_parser = FindCompatibleDTS()
    lines = compatibles_parser.run(scriptLines('get-blob', hash), family)
    comps = collect_get_blob_output(lines)

    return (idx, family, comps)

# Collect compatible documentation references for a single file
def get_comps_docs(file_id: FileId) -> Optional[Tuple[int, str, LinesListDict]]:
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
def update_version(db: DB, tag: bytes, pool: Pool, dts_comp_support: bool):
    idx_to_hash_and_filename = collect_blobs(db, tag)
    def_cache = {}

    # Collect blobs to process and split list of blobs into chunks
    idxes = [(idx, hash, filename) for (idx, (hash, filename)) in idx_to_hash_and_filename.items()]
    chunksize = int(len(idxes) / cpu_count())
    chunksize = min(max(1, chunksize), 100)

    collect_blobs(db, tag)
    logger.info("collecting blobs done")

    for result in pool.imap_unordered(get_defs, idxes, chunksize):
        if result is not None:
            add_defs(db, def_cache, result)

    logger.info("defs done")

    for result in pool.imap_unordered(get_docs, idxes, chunksize):
        if result is not None:
            add_docs(db, *result)

    logger.info("docs done")

    if dts_comp_support:
        for result in pool.imap_unordered(get_comps, idxes, chunksize):
            if result is not None:
                add_comps(db, *result)

        logger.info("dts comps done")

        for result in pool.imap_unordered(get_comps_docs, idxes, chunksize):
            if result is not None:
                add_comps_docs(db, *result)

        logger.info("dts comps docs done")

    for result in pool.imap_unordered(get_refs, idxes, chunksize):
        if result is not None:
            add_refs(db, def_cache, result)

    logger.info("refs done")

    logger.info("update done")

def create_database(filename):
    db = duckdb.connect(filename)
    db.sql("create sequence if not exists file_seq start 1")
    db.sql("""create table if not exists file (
        id integer primary key default nextval('file_seq'),
        hash varchar,
        path varchar,
    )""")
    db.sql("""create table if not exists defs (
        ident varchar,
        file_id integer references file(id),
        type varchar,
        line int,
        family varchar,
    )""")
    db.sql("""create table if not exists refs (
        ident varchar,
        file_id integer references file(id),
        family varchar,
        line int,
    )""")
    db.sql("""create table if not exists docs (
        ident varchar,
        file_id integer references file(id),
        family varchar,
        line int,
    )""")
    db.sql("""create table if not exists comps (
        ident varchar,
        file_id integer references file(id),
        family varchar,
        line int,
    )""")
    db.sql("""create table if not exists comps_docs (
        ident varchar,
        file_id integer references file(id),
        family varchar,
        line int,
    )""")
    db.sql("""create table if not exists versions (
        version varchar,
        file_id integer references file(id),
    )""")

    return db

def vers_exists(db, version):
    return db.execute("select 1 from versions where version=?", [version]).fetchone()

if __name__ == "__main__":
    dts_comp_support = bool(int(script('dts-comp')))

    db = create_database("test.db")
    print(vers_exists(db, '1'))

    with Pool() as pool:
        for tag in scriptLines('list-tags'):
            if not vers_exists(db, tag):
                logger.info("updating tag %s", tag)
                update_version(db, tag, pool, dts_comp_support)
                db.close()
                db = None
                break

