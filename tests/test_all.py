import logging
import ldap

from tests.base_test import BaseTest

logger = logging.getLogger(__name__)

class TestAll(BaseTest):

    def test_ldap_server(self):
        # There must be exactly one dn for the search
        # basedn, SCOPE: BASE
        base = self.dst.find(self.dst_conf['basedn'], scope=ldap.SCOPE_BASE)
        logger.info(f"base: {base}")

        services = self.dst.find("dc=services,{}".format(self.dst_conf['basedn']), scope=ldap.SCOPE_BASE)
        logger.info(f"services: {services}")
        # assert len(services) == 1

        # Now iterate through SBS API calls and verify that corresponding LDAP objects & attributes exist...

        for s in self.src.service_collaborations():
            logger.info(f"Testing service: {s} ...")

            service = self.dst.find("dc=ordered,dc={},{}".format(s, self.dst_conf['basedn']), scope=ldap.SCOPE_BASE)
            logger.info(f"service: {service}")

        # assert len(base) == 1