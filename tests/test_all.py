import logging

from tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class TestAll(BaseTest):

    def setUp(self):
        super().setUp()
        self.users = self.src.all_users()

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
                logger.error("No results for: {}".format(rdn))

            logger.debug("Result: {}".format(r))

            self.assertTrue(r)
            return r

        def check_people(rdn, people, context_checks):
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

                # Here a sequence of function can be initiated to verify this person in a particular context
                for f in context_checks:
                    f(u, user_object)

        def check_group(rdn, group, members):
            """ Check that group object exists and members are defined
            """

            check_object(rdn)

            group_object = check_object(f"cn={group},{rdn}")

            # Now we check that de LDAP group actually contains the 'active' members.
            # 'expired' members are excluded since they should not
            # appear in any group. (According to pivotal: #180730988)

            active_members = []
            for m in members:
                logger.debug(f"member: {m['user']['username']}, status: {m['status']}")
                if m['status'] == 'active':
                    active_members.append(m)

            if len(active_members) > 0:
                member_element = group_object[list(group_object)[0]]['member']

                for m in member_element:
                    logger.debug(f"Found member: {m}")

                found_members = [m.split(',')[0].split('=')[1] for m in member_element]
                required_members = [m['user']['username'] for m in active_members]

                assert(sorted(found_members) == sorted(required_members))

        def check_ldap(rdn, people, groups, group_name_function, context_checks=[]):
            """ check for ordered object entry and check both people and object subtrees
            """
            check_object(rdn)

            check_people(f"ou=people,{rdn}", people, context_checks)
            check_group(f"ou=groups,{rdn}", group_name_function("@all"), people)

            for g in groups:
                check_group(f"ou=groups,{rdn}", group_name_function(g['short_name']), g['collaboration_memberships'])

        for c in self.src.collaborations():
            logger.info(f"* Checking collaboration: {c['name']}")

            detail = self.src.collaboration(c['id'])
            for s in detail['services']:

                def check_ordered_person_expiry(person, _):
                    # When CO is expired, the person in de Ordered Subtree should mut be expired as well
                    if detail['status'] == 'expired':
                        logger.debug(f"Checking expiry status of {person['user']['username']}")
                        assert([person['status'], 'expired'])

                def check_accepted_policy_agreement(person, person_object):
                    # Verify that AUP attribute exists when accepted by user for this service
                    # and not exists when not (yet) accepted by the user...

                    username = person['user']['username']

                    aup_found = False

                    for u in self.users:
                        if u['username'] == username:
                            assert('accepted_aups' in u)

                            for aup in u['accepted_aups']:
                                assert('service_id' in aup)

                                if aup['service_id'] == s['id']:
                                    aup_found = True
                                    break

                            break

                    if 'voPersonPolicyAgreement' in person_object[list(person_object)[0]]:
                        assert(aup_found)
                    else:
                        assert(not aup_found)

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
                    group_name_ordered,
                    context_checks=[
                        check_ordered_person_expiry,
                        check_accepted_policy_agreement
                    ]
                )

                check_ldap(
                    f"dc=flat,dc={s['entity_id']},{self.dst_conf['basedn']}",
                    detail['collaboration_memberships'],
                    detail['groups'],
                    group_name_flat
                )

                logger.info(f"*** Checking Admin account: {s['entity_id']}")
                assert('ldap_password' in s)
                admin_object = check_object(f"cn=admin,dc={s['entity_id']},{self.dst_conf['basedn']}", expected_count=1)
                ldap_password = s['ldap_password']
                if ldap_password:
                    userPassword = admin_object[list(admin_object)[0]]['userPassword']
                    assert(userPassword == '{CRYPT}' + ldap_password)
