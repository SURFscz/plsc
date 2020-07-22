#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Stop previous server
killall json-server

# Start API server and record pid
/usr/bin/env json-server sbs.json &

# Wait for API server
while ! nc -z localhost 3000 ; do sleep 0.1 ; done
