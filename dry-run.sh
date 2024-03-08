#!/bin/sh
docker stop plsc-ldap-1
docker rm plsc-ldap-1
docker compose up -d
sleep 5
docker exec plsc-ldap-1 slapmodify -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_1.ldif
docker exec plsc-ldap-1 slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 0 -l /opt/ldap/ldif/config_2.ldif
docker exec plsc-ldap-1 slapadd    -F /opt/bitnami/openldap/etc/slapd.d/ -n 2 -l /backup.ldif
./run.sh misc/plsc_test.yml
