#!/bin/sh

set -e
set -o pipefail

cd /tmp
poetry install

rm /tmp/poetry.lock /tmp/pyproject.toml
rm /tmp/docker-install-project.sh
