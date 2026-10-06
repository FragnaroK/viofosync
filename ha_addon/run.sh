#!/usr/bin/env bash
set -e

mkdir -p /config /recordings
chown dashcam:dashcam /config /recordings

exec /entrypoint.sh
