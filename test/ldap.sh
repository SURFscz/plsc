#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR
if [ -f slapd.pid ]; then
    kill $(cat slapd.pid)
fi
rm -rf data/*.mdb
slapd -4 -f slapd.conf -h ldap://localhost:8389/
ldapadd -H ldap://localhost:8389 -D cn=admin,dc=sram,dc=tld -w secret -f sram.ldif
PID=`pidof slapd`
echo "PID: $PID"
echo $PID > slapd.pid
