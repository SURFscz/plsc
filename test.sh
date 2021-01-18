#!/bin/bash

source .env

# Setup LDAP server
# etc/ldap_start.sh

# Setup json API server
etc/api_start.sh

cat <<EOF >/tmp/plsc-test.yml
---
ldap:
  src:
    uri: ${LDAP_URL}
    basedn: ${LDAP_BASE_DN}
    binddn: ${LDAP_BIND_DN}
    passwd: ${LDAP_ADMIN_PASSWORD}
  dst:
    uri: ${LDAP_URL}
    basedn: dc=services,${LDAP_BASE_DN}
    binddn: ${LDAP_BIND_DN}
    passwd: ${LDAP_ADMIN_PASSWORD}
sbs:
  src:
    host: ${SBS_URL}
    user: sysread
    passwd: ${SBS_PASSWORD}
    ipv4_only: True
EOF

# slp-ordered testrun
/usr/bin/env python slp-ordered.py /tmp/plsc-test.yml

# plsc-flat testrun
/usr/bin/env python plsc-flat.py /tmp/plsc-test.yml

# Check LDAP
/usr/bin/env pytest tests

# Stop API server
# etc/api_stop.sh

# Stop LDAP serveruser
etc/ldap_stop.sh
