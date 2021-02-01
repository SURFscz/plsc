#!/bin/bash

source .env

# Display result...
docker exec my-ldap ldapsearch -H ldap://localhost -b "${LDAP_BASE_DN:-dc=example,dc=org}" -D "${LDAP_BIND_DN:-cn=admin,dc=example,dc=org}" -w "${LDAP_ADMIN_PASSWORD:-changeme}"
