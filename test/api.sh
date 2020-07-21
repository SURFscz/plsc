#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Kill previous server
if [ -f api.pid ]; then
    kill $(cat api.pid)
fi

# Start API server and record pid
/usr/bin/env json-server test/sbs.json &>/dev/null &
PID=$!
echo $PID > api.pid
echo "PID: $PID"

# Wait for API server
while ! nc -z localhost 3000 ; do sleep 0.1 ; done
