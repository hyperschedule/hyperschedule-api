#!/bin/sh

set -e
set -o pipefail

# Installing lxml and psutil here means we don't need to build them
# from source (which happens if we install them via Pip). We need
# util-linux for the column utility used in 'make help'.
packages="

make
py3-lxml
py3-psutil
python3
util-linux

"

apk add --no-cache $packages

# Use poetry to install project dependencies. We can't just use Pip
# because we need to parse poetry.lock.
pip3 --disable-pip-version-check install poetry==0.12.16

# We need to do this because Poetry doesn't know how to look for
# python3/pip3, and instead is hardcoded to use python/pip.
ln -s python3 /usr/bin/python
ln -s pip3 /usr/bin/pip

# Install dependencies globally inside Docker.
poetry config settings.virtualenvs.create false

rm /tmp/docker-install-system.sh
