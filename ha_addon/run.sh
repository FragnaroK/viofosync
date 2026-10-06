#!/usr/bin/env bash
set -e

# Keep clips in their own folder rather than the root of the shared media dir.
export RECORDINGS=/recordings/viofosync

mkdir -p /config "$RECORDINGS"
chown dashcam:dashcam /config "$RECORDINGS"

# Ingress already authenticates through Home Assistant.
if [[ "$(python3 -c 'import json;print(json.load(open("/data/options.json")).get("disable_auth", True))' 2>/dev/null)" == "True" ]]; then
    export DISABLE_AUTH=1
fi

exec /entrypoint.sh
