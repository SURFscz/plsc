#!/bin/bash

set -e
shopt -s extglob  # for the string postfix matching below

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

COMPOSE_FILE="docker-compose.yml"
COMPOSE="docker compose --file ${COMPOSE_FILE}"

echo "Starting containers"
${COMPOSE} kill && ${COMPOSE} rm -f || true
${COMPOSE} up --detach
sleep 5

echo "Configuring LDAP"
${COMPOSE} exec ldap slapmodify -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_1.ldif
${COMPOSE} exec ldap slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_2.ldif

echo "Loading data"
${COMPOSE} exec ldap slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 2 -l /backup.ldif

echo "Running plsc"
export PATH=$(pwd)/venv/bin:${PATH}
../run.sh ./plsc_dryrun.yml

exit 0