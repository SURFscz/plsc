import logging

from tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class TestAll(BaseTest):

    def test_ldap_services(self):
        """ this test will traverse the SBS structure and verify
        that all relevant components are registered as expected in LDAP
        """

        def check_object(rdn, expected_count=None):
            """ Check for LDAP rdn entry
            return object if found, raise assertion if not
            """

            logger.info(f"*** Checking LDAP: {rdn}")

            r = self.dst.find(rdn)

            if expected_count:
                assert(len(r) == expected_count)

            if not r:
                logger.info("No results for: {}".format(rdn))

            logger.debug("Result: {}".format(r))

            self.assertTrue(r)
            return r

        def check_people(rdn, people):
            """ Check that people object exists and that users exists
            """
            check_object(rdn)

            for u in people:
                user_object = check_object(f"uid={u['user']['username']},{rdn}")

                # Specify as much of tests to see that all LDAP entries are correct

                # Example: verify that ssh Public key and objectClass is present
                # when SBS user profile has ssh_keys...
                if u['user'].get('ssh_keys', None):
                    assert('ldapPublicKey' in user_object[list(user_object)[0]]['objectClass'])
                    assert('sshPublicKey' in user_object[list(user_object)[0]].keys())

        def check_group(rdn, group, members):
            """ Check that group object exists and members are defined
            """

            check_object(rdn)

            for m in members:
                logger.debug(f"Need member: {m['user']['username']}")

            if len(members) > 0:
                group_object = check_object(f"cn={group},{rdn}")
                member_element = group_object[list(group_object)[0]]['member']

                for m in member_element:
                    logger.debug(f"Found member: {m}")

                found_members = [m.split(',')[0].split('=')[1] for m in member_element]
                required_members = [m['user']['username'] for m in members]

                assert(sorted(found_members) == sorted(required_members))

        def check_ldap(rdn, people, groups, group_name_function):
            """ check for ordered object entry and check both people and object subtrees
            """
            check_object(rdn)

            check_people(f"ou=people,{rdn}", people)
            check_group(f"ou=groups,{rdn}", group_name_function("@all"), people)

            for g in groups:
                check_group(f"ou=groups,{rdn}", group_name_function(g['short_name']), g['collaboration_memberships'])

        for c in self.src.collaborations():
            logger.info(f"* Checking collanboration: {c['name']}")

            detail = self.src.collaboration(c['id'])
            for s in detail['services']:
                org_sname = c['organisation']['short_name']

                def group_name_ordered(g):
                    return g

                def group_name_flat(g):
                    return f"{org_sname}.{c['short_name']}.{g}"

                logger.info(f"** Checking Service: {s['entity_id']}")

                check_ldap(
                    f"o={org_sname}.{c['short_name']},dc=ordered,dc={s['entity_id']},{self.dst_conf['basedn']}",
                    detail['collaboration_memberships'],
                    detail['groups'],
                    group_name_ordered
                )

                check_ldap(
                    f"dc=flat,dc={s['entity_id']},{self.dst_conf['basedn']}",
                    detail['collaboration_memberships'],
                    detail['groups'],
                    group_name_flat
                )
