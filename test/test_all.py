import logging
import pytest
import requests
import ldap
from plsc.test.base_test import BaseTest

logger = logging.getLogger(__name__)

class TestAll(BaseTest):

    def test_api_server(self):
        logger.debug("test_foobar")
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
