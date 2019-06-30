#!/bin/sh

if [ "$OSTYPE" != darwin* ] && [ "$EUID" != 0 ]; then
    sudo docker "$@"
else
    docker "$@"
fi
