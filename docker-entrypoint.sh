#!/bin/sh
# Seed the persistent /app/data volume on first boot, then hand off to CMD.
#
# The image ships a baked copy of the catalogue at /app/seed (a path OUTSIDE the
# volume, so the volume mount can't hide it). On startup we copy it into the
# volume ONLY if the volume doesn't already have a catalogue -- so the very first
# run gets a working catalogue, and every run after that keeps the live one that
# `jobsearch.refresh` has been updating in place. The freshness baseline and HTTP
# cache under /app/data are likewise preserved.
set -e

mkdir -p /app/data/cache

if [ ! -f /app/data/catalogue.json ] && [ -f /app/seed/catalogue.json ]; then
    echo "[entrypoint] empty data volume -> seeding catalogue.json from image"
    cp /app/seed/catalogue.json /app/data/catalogue.json
fi

exec "$@"
