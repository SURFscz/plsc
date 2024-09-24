#!/bin/sh
docker rm ldap || true
docker run -d \
    -e "LDAP_SEED_INTERNAL_SCHEMA_PATH=/opt/misc/schema" \
    -e "LDAP_DOMAIN=services.sram.tld" \
    -e "LDAP_ADMIN_USERNAME=admin" \
    -e "LDAP_ADMIN_PASSWORD=secret" \
    -e "LDAP_CONFIG_PASSWORD=config" \
    -e "LDAP_BASE_DN=dc=services,dc=sram,dc=tld" \
    -e "LDAP_TLS=true" \
    -v "./misc/schema:/opt/misc/schema" \
    -p 389:389 \
    --name ldap \
    osixia/openldap:latest
