#!/bin/sh

#LXR_DATA_DIR=./data/glibc/data LXR_REPO_DIR=./data/glibc/repo hyperfine -i --min-runs 3 --show-output --export-markdown benchmark-table.md \
#    --parameter-list update 'python3 -m elixir.file_update, ELIXIR_THREADING=1 python3 -m elixir.update, ELIXIR_CACHE=1 python3 -m elixir.update,python3 -m elixir.update,python3 -m elixir.non_gen_update' \
#    --prepare 'rm -rf data/glibc/data/*' \
#    '{update}'

LXR_DATA_DIR=./data/linux/data LXR_REPO_DIR=./data/linux/repo hyperfine -i --min-runs 3 --show-output --export-markdown benchmark-table-linux-rest.md \
    --parameter-list update 'python3 -m elixir.update,python3 -m elixir.non_gen_update' \
    --prepare 'rm -rf data/linux/data/*' \
    '{update}'

LXR_DATA_DIR=./data/linux/data LXR_REPO_DIR=./data/linux/repo hyperfine -i --min-runs 1 --show-output --export-markdown benchmark-table-linux-once.md \
    --parameter-list update 'python3 -m elixir.file_update, ELIXIR_THREADING=1 python3 -m elixir.update, ELIXIR_CACHE=1 python3 -m elixir.update,python3 -m elixir.update,python3 -m elixir.non_gen_update' \
    --prepare 'rm -rf data/linux/data/*' \
    '{update}'

