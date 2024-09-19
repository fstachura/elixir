import sys
import re
import bsddb3
import subprocess
from elixir.data import RefList

def run_cmd(*args, env=None):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if len(p.stderr) != 0:
        print('command', args, 'printed to stderr:', p.stderr.decode('utf-8'))
    return p.stdout, p.returncode


def get_file_git(repo_path, filename):
    file_result, _ = run_cmd("git", "-C", repo_path, "cat-file", "blob", filename)
    return file_result.split(b'\n')

def get_file_repo_single_version(repo_path, filename):
    split_filename = filename.split(":")
    with open(f'{ repo_path }/{ ":".join(split_filename[1:]) }', 'rb') as f:
        return f.read().split(b'\n')

# NOTE this only works on a single version

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} db_path repo_path")
        exit(1)

    db_path = sys.argv[1]
    repo_path = sys.argv[2]

    refs_db = bsddb3.db.DB()
    refs_db.open(f"{db_path}/references.db", flags=bsddb3.db.DB_RDONLY)

    versions_db = bsddb3.db.DB()
    versions_db.open(f"{db_path}/versions.db", flags=bsddb3.db.DB_RDONLY)

    #get_file = get_file_git
    get_file = get_file_repo_single_version

    id_to_filename = {}
    for k, v in versions_db.items():
        for line in v.split(b"\n"):
            if len(line) != 0:
                split_line = line.split(b" ")
                file_id = split_line[0]
                path = b" ".join(split_line[1:])
                id_to_filename[int(file_id.decode())] = k.decode() + ":" + path.decode()

    for k, v in refs_db.items():
        for file_id, lines, family in RefList(v).iter():
            first_line_printed = False
            filename = id_to_filename[file_id]

            lines_file = get_file(repo_path, filename)

            for line in lines.split(","):
                try:
                    file_line = lines_file[int(line)-1].decode()
                except UnicodeDecodeError:
                    file_line = lines_file[int(line)-1].decode('latin-1')

                print(filename, k.decode(),line, file_line)

