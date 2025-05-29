#!/bin/sh

#LXR_DATA_DIR=./data/glibc/data LXR_REPO_DIR=./data/glibc/repo hyperfine -i --min-runs 3 --show-output --export-markdown benchmark-table.md \
#    --parameter-list update 'python3 -m elixir.file_update, ELIXIR_THREADING=1 python3 -m elixir.update, ELIXIR_CACHE=1 python3 -m elixir.update,python3 -m elixir.update,python3 -m elixir.non_gen_update' \
#    --prepare 'rm -rf data/glibc/data/*' \
#    '{update}'

export PYTHONUNBUFFERED=1
export PROJECT=linux
export LXR_REPO_DIR=/srv/elixir-data/$PROJECT/repo
export LXR_DATA_DIR=/srv/elixir-data/$PROJECT/data-faster-update
export MD_NAME=benchmark-table-$PROJECT.md

# ELIXIR_THREADING=1 python3 -m elixir.update

./script.sh list-tags

hyperfine -i --min-runs 3 --show-output --export-markdown $MD_NAME \
    --prepare 'rm -rf $LXR_DATA_DIR/*; mkdir -p $LXR_DATA_DIR' \
    --cleanup 'rm -f /tmp/refs /tmp/defs; rm -rf $LXR_DATA_DIR/*;' \
    --parameter-list update 'python3 -m elixir.file_update, python3 -m elixir.update_simplified, ELIXIR_CACHE=1 python3 -m elixir.update, python3 -m elixir.update, python3 -m elixir.gen_update' \
    '{update}'

hyperfine -i --min-runs 3 --show-output --export-markdown old-update-$MD_NAME \
    --prepare 'du -had1 $LXR_DATA_DIR >> sizes; echo >> sizes; rm -rf $LXR_DATA_DIR/*; mkdir -p $LXR_DATA_DIR' \
    --parameter-list update 'python3 update.py 128' \
    '{update}'

