#!/bin/bash

set -e

clean_git_worktree() {
    find $1 -mindepth 1 -maxdepth 1 -type d -not -path "$1/.git*" -exec rm -r {} \; || true
    find $1 -mindepth 1 -maxdepth 1 -type f -not -path "$1/.git*" -exec rm -r {} \; || true
}

copy_git_worktree() {
    echo $1 $2
    rsync -q -av $1 --exclude .git $2
}

resolve_path() {
    project_path_resolved=`readlink -m $1`
    echo ./`realpath -m --relative-to=$(pwd) $project_path_resolved`
}

print_readme() {
    echo "This directory contains projects specified in west.yaml."
    echo "It was generated automatically and is not a part of the upstream $PROJECT_NAME repository."
    echo "You can report bugs (ex. missing west.yaml projects) at https://github.com/bootlin/elixir"
}

if [[ "$#" -ne 1 ]]; then
    echo "usage: $0 west-project-dir"
    exit 1
fi

if ! command -v west 2>&1 >/dev/null; then
    echo "west command is not available"
    exit 1
fi

cd $1

PROJECT_NAME=zephyr
TOP_DIR=./west-topdir
REPO_DIR=./repo
export ZEPHYR_BASE=$TOP_DIR

mkdir -p $TOP_DIR
mkdir -p $REPO_DIR

if [[ ! -d $TOP_DIR/.west ]]; then
    west init $TOP_DIR
fi

if [[ ! -d $REPO_DIR/.git ]]; then
    mkdir -p $REPO_DIR
    git -C $REPO_DIR init
    git -C $REPO_DIR config user.email elixir@bootlin.com
    git -C $REPO_DIR config user.name "west repository converter for $PROJECT_NAME"
fi

project_tags=`git -C $TOP_DIR/$PROJECT_NAME tag | grep -v "^$PROJECT_NAME"`
local_tags=`git -C $REPO_DIR tag`
new_tags=`echo $project_tags $local_tags | tr ' ' '\n' | sort | uniq -u`

for tag in $new_tags; do
    echo "found missing tag $tag"
    git -C $TOP_DIR/$PROJECT_NAME checkout -f $tag
    clean_git_worktree $REPO_DIR

    west_manifest=$TOP_DIR/$PROJECT_NAME/west.yml
    if [[ -f $west_manifest ]]; then
        # Find disabled groups
        extra_group_names=`cat west-topdir/zephyr/west.yml | yq -r '(.manifest."group-filter" // [])[]'`
        # Take only disabled groups (start with '-'), enable them (replace - with +),
        # concatenate lines to group-a,group-b,...
        extra_groups=`echo $extra_group_names | tr ' ' '\n' | grep '^-' | sed 's/^-/+/' | paste -s -d,`
        west update $([[ ! -z $extra_groups ]] && echo --group-filter "$extra_groups")
        # Get module paths to copy
        module_paths=`cat $west_manifest | yq -r '.manifest.projects | map(.path)[] | select(. != null)'`

        mkdir -p $REPO_DIR/west_projects
        for top_path in $module_paths; do
            # Check if project_path does not traverse outside west_projects
            project_path=`resolve_path $REPO_DIR/west_projects/$top_path`
            if [[ $project_path =~ ^$REPO_DIR/west_projects/.* ]]; then
                echo "copying $top_path project directory"
                mkdir -p $project_path
                copy_git_worktree $TOP_DIR/$top_path/ $project_path
            else
                echo "found suspicious path $project_path, not copying"
            fi
        done

        print_readme > $REPO_DIR/west_projects/README.txt
    fi

    echo "copying $PROJECT_NAME directory"
    git -C $REPO_DIR checkout master
    copy_git_worktree $TOP_DIR/$PROJECT_NAME/ $REPO_DIR

    echo "commiting $tag"
    git -C $REPO_DIR add '*'
    git -C $REPO_DIR commit -q -a -m $tag
    git -C $REPO_DIR tag $tag
done

