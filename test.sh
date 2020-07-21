#!/bin/sh

# Setup LDAP server
test/ldap.sh

# slp-ordered testrun
/usr/bin/env python slp-ordered test/plsc.yml

# Check LDAP
/usr/bin/env pytest test
