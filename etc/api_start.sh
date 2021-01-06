#!/bin/bash

source .env

etc/api_stop.sh 2>&1 >/dev/null

# Start API server and record pid
/usr/bin/env json-server -b :${SBS_PORT:-3000} etc/sbs.json &

# Wait for API server
while ! nc -z localhost ${SBS_PORT:-3000} ; do sleep 0.1 ; done
