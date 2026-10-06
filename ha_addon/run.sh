#!/usr/bin/env bash
set -e

mkdir -p /config /recordings
chown dashcam:dashcam /config /recordings

# Ingress already authenticates through Home Assistant.
if [[ "$(python3 -c 'import json;print(json.load(open("/data/options.json")).get("disable_auth", True))' 2>/dev/null)" == "True" ]]; then
    export DISABLE_AUTH=1
fi

exec /entrypoint.sh
