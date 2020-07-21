#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Kill previous server
if [ -f slapd.pid ]; then
    kill $(cat slapd.pid)
fi

# Cleanup
rm -rf data/*.mdb

# Start LDAP server and record pid
slapd -d -4 -f slapd.conf -h ldap://localhost:8389/ &>/dev/null &
PID=$!
echo $PID > slapd.pid
echo "PID: $PID"

# Wait for slapd
while ! nc -z localhost 8389 ; do sleep 0.1 ; done

# Add schemas
ldapadd -H ldap://localhost:8389 -D cn=admin,cn=config -w config -f eduPerson.ldif
ldapadd -H ldap://localhost:8389 -D cn=admin,cn=config -w config -f voPerson.ldif
ldapadd -H ldap://localhost:8389 -D cn=admin,cn=config -w config -f sczGroup.ldif

# Add basedn
ldapadd -H ldap://localhost:8389 -D cn=admin,dc=sram,dc=tld -w secret -f sram.ldif
