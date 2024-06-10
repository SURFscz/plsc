#!/bin/bash

set -e
shopt -s extglob  # for the string postfix matching below

cleanup() {
    [ -n "$COMPOSE"   ] && ${COMPOSE} rm --force --stop >/dev/null 2>&1 || true
    [ -n "$SOCAT_PID" ] && kill "$SOCAT_PID" || true
    [ -n "$TMPFILE"   ] && rm -f "${TMPFILE}" || true
}
trap cleanup EXIT

# check if data file are present
if [ ! -f "backup.ldif" ] || [ ! -f "sync.json" ]; then
    echo "Data files backup.ldif and/or sync.json not found"
    echo "Copy ldap backup (slapcat -n1 output) to backup.ldif"
    echo "Copy SBS plsc sync output to sync.json"
    exit 1
fi

GREEN="\033[0;32m"
NORMAL="\033[0m"

# check if we're using a remote docker host
# in that case, we need to forward the local port 1389 to the real docker host
# because all scripts depend on the ldap being available locally
docker_host=$(docker context inspect -f '{{ .Endpoints.docker.Host }}')
docker_proto=${docker_host:0:6}
if [ "$docker_proto" == "tcp://" ]; then
    # remove protocol
    HOST=${docker_host:6}
    # remove port number
    HOST=${HOST%:+([[:digit:]])?(/)}

    echo "Using remote docker host $HOST ($docker_host)"
    socat "TCP4-LISTEN:1389,fork,reuseaddr" "TCP4:${HOST}:1389" 2>/dev/null &
    SOCAT_PID=$!
fi


# find basedn
BASEDN=$( awk '/^dn: / { print $2; exit }' backup.ldif )
export BASEDN
echo "Found basedn '$BASEDN'"

COMPOSE_FILE="docker-compose.yml"
COMPOSE="docker compose --file ${COMPOSE_FILE}"

echo -n "Starting containers..."
${COMPOSE} rm --force --stop >/dev/null 2>&1 || true
${COMPOSE} up --detach       >/dev/null 2>&1
echo

echo -n "Waiting for ldap to start"
while sleep 0.2
do
    echo -n "."
    if docker compose logs | grep -q '\*\* Starting slapd \*\*'
    then
        echo " Up!"
        break
    fi
done

echo "Configuring LDAP"
${COMPOSE} exec ldap ldapmodify -H ldap://localhost:1389/ -D cn=admin,cn=config -w changethispassword -f /opt/ldap/ldif/config_1.ldif > /dev/null 2>&1
${COMPOSE} exec ldap ldapadd    -H ldap://localhost:1389/ -D cn=admin,cn=config -w changethispassword -f /opt/ldap/ldif/config_2.ldif > /dev/null 2>&1

echo "Loading data"
${COMPOSE} exec ldap slapadd  -q -F /opt/bitnami/openldap/etc/slapd.d/ -n 2 -l /backup.ldif  2>/dev/null

# generate plsc config
echo "Generating plsc config"
TMPFILE=$(mktemp -t plsc_XXXXXX.yml)
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

# install venv
if ! test -d '../venv'
then
    echo -n "Installing venv..."
    python3 -mvenv ../venv
    ../venv/bin/pip install -q --upgrade pip wheel setuptools
    ../venv/bin/pip install -q -r ../requirements.txt
    echo
fi


#export LOGLEVEL=DEBUG
echo "Running plsc"
(
    cd ..
    export PATH="$(pwd)/venv/bin:${PATH}"
    ./run.sh "${TMPFILE}"
)

echo Dumping result
docker-compose -f docker-compose.yml exec -ti ldap slapcat -F /opt/bitnami/openldap/etc/slapd.d/ -o ldif-wrap=no -n2 > result.ldif 2>/dev/null

echo Comparing result
../venv/bin/python ./ldifparser.py < backup.ldif > backup.ldif.parsed
../venv/bin/python ./ldifparser.py < result.ldif > result.ldif.parsed
diff --unified --text --color=always backup.ldif.parsed result.ldif.parsed && echo -e "${GREEN}No changes detected!${NORMAAL}"

exit 0