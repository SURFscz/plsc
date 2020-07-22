import logging
import pytest
import requests
import ldap
from plsc.test.base_test import BaseTest

logger = logging.getLogger(__name__)

class TestAll(BaseTest):

    def test_api_server(self):
        # Test if the SBS API server is running
        url = 'http://localhost:3000/version'
        r = requests.get(url).json()
        logger.debug(f"json: {r}")
        assert r == "1.0"

    def test_ldap_server(self):
        # There must be exactly one dn for the search
        # basedn, SCOPE: BASE
        base = self.dst.find(self.dst_conf['basedn'], scope=ldap.SCOPE_BASE)
        logger.debug(f"base: {base}")
        assert len(base) == 1

    def test_ldap_ordered_coffee(self):
        # There must be exactly one dn for the search
        # cn=Coffee...,dc=ordered..., SCOPE: BASE
        coffee = self.dst.find('cn=Coffee,ou=Groups,o=SURF:first,dc=ordered,dc=http://flop.nl,dc=sram,dc=tld', scope=ldap.SCOPE_BASE)
        logger.debug(f"coffee: {coffee}")
        assert len(coffee) == 1

    def test_ldap_flat_coffee(self):
        # There must be exactly one dn for the search
        # cn=Coffee...,dc=flat..., SCOPE: BASE
        coffee = self.dst.find('cn=Coffee,ou=Groups,dc=flat,dc=http://flop.nl,dc=sram,dc=tld', scope=ldap.SCOPE_BASE)
        logger.debug(f"coffee: {coffee}")
        assert len(coffee) == 1
