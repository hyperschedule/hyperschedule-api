#!/bin/sh

export HYPERSCHEDULE_HOST=0.0.0.0
export HYPERSCHEDULE_PORT=80

cd /src
if [[ -n "$1" ]]; then
    make $1
fi
