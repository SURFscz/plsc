import logging
import pytest
import requests
import ldap
from plsc.test.base_test import BaseTest
from plsc.sldap import sLDAP

logger = logging.getLogger(__name__)

dst_conf = {
    'uri': 'ldap://localhost:8389',
    'basedn': 'dc=sram,dc=tld',
    'binddn': 'cn=admin,dc=sram,dc=tld',
    'passwd': 'secret'
}

class TestFoobar(BaseTest):

    def test_foobar(self):
        logger.debug("test_foobar")
        url = 'http://localhost:3000/people/1'
        r = requests.get(url).json()
        logger.debug(f"json: {r}")
        assert r['name'] == "harry"

    def test_ldap_server(self):
        # There must be exactly one dn for the search
        # basedn, SCOPE_BASE
        dst = sLDAP(dst_conf)
        base = dst.find(dst_conf['basedn'], scope=ldap.SCOPE_BASE)
        logger.debug(f"base: {base}")
        assert len(base) == 1
