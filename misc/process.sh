#!/bin/bash
set -e
echo "PLSC loop started"
while true
do
    sleep 5m
    /opt/plsc/run.sh plsc.yml
done

exit 0
