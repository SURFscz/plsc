#!/bin/bash

if [ -f .env ]; then
  source .env
else
  source .test.env
fi

# Set CONTAINER_TOOL to 'docker' if not defined
CONTAINER_TOOL=${CONTAINER_TOOL:-docker}

# Display result...
$CONTAINER_TOOL exec my-ldap ldapsearch -x -H ldap://localhost -b "${LDAP_BASE_DN:-dc=example,dc=org}"
