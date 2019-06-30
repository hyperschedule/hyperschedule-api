#!/bin/sh

set -e
set -o pipefail

apk add --no-cache wget

cd /tmp
wget -nv https://github.com/watchexec/watchexec/releases/download/1.10.2/watchexec-1.10.2-x86_64-unknown-linux-musl.tar.gz
tar -xzvf watchexec-*.tar.gz
mv watchexec-*/watchexec /usr/bin/
rm -rf watchexec-*

rm /tmp/docker-install-system-dev.sh
