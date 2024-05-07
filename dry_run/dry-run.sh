#!/bin/bash

set -e
shopt -s extglob  # for the string postfix matching below

# check if data file are present
if [ ! -f "backup.ldif" -o ! -f "sync.json" ]; then
    echo "Data files backup.ldif and/or sync.json not found"
    echo "Copy ldap backup (slapcat -n1 output) to backup.ldif"
    echo "Copy SBS plsc sync output to sync.json"
    exit 1
fi

# check if we're using a remote docker host
docker_host=$(docker context inspect -f '{{ .Endpoints.docker.Host }}')
docker_proto=${docker_host:0:6}
if [ "$docker_proto" == "tcp://" ]; then
    # remove protocol
    HOST=${docker_host:6}
    # remove port number
    HOST=${HOST%:+([[:digit:]])?(/)}

    echo "Using remote docker host $HOST ($docker_host)"
    socat TCP4-LISTEN:1389,fork,reuseaddr TCP4:$HOST:1389 &
    BG_PID=$!

    # kill socat when exiting
    trap "kill $BG_PID" EXIT
fi


# find basedn
export BASEDN=$( awk '/^dn: / { print $2; exit }' backup.ldif )
echo "Found basedn '$BASEDN'"

COMPOSE_FILE="docker-compose.yml"
COMPOSE="docker compose --file ${COMPOSE_FILE}"

echo "Starting containers"
${COMPOSE} rm --force --stop || true
${COMPOSE} up --detach

echo -n "Waiting for ldap to start"
while sleep 0.5
do
    echo -n "."
    if docker compose logs | grep -q '\*\* Starting slapd \*\*'
    then
        echo " Up!"
        break
    fi
done

echo "Configuring LDAP"
${COMPOSE} exec ldap slapmodify -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_1.ldif
${COMPOSE} exec ldap slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_2.ldif

echo "Loading data"
${COMPOSE} exec ldap slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 2 -l /backup.ldif

# generate plsc config
echo "Generating plsc config"
TMPFILE=$(mktemp plsc_XXXXXX.yml)
trap "rm -f $TMPFILE" EXIT
cat <<EOF | sed 's/^    //' > "${TMPFILE}"
    ---
    ldap:
      src:
        uri: "ldap://localhost:1389/"
        basedn: "${BASEDN}"
        binddn: "cn=admin,${BASEDN}"
        passwd: "changethispassword"
        sizelimit: 5
      dst:
        uri: "ldap://localhost:1389/"
        basedn: "${BASEDN}"
        binddn: "cn=admin,${BASEDN}"
        passwd: "changethispassword"
        sizelimit: 5
    sbs:
      src:
        host: "test"
        sync: "dry_run/sync.json"
    pwd: '{CRYPT}!'
    uid: 1000
    gid: 1000
EOF

export LOGLEVEL=DEBUG
echo "Running plsc"
cd ..
export PATH=$(pwd)/venv/bin:${PATH}
./run.sh "./dry_run/${TMPFILE}"

exit 0