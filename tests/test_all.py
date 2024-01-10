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

        def object_count(rdn):
            """ Return the nur of objects that exists under this rdn
            """

            logger.info(f"*** Object count LDAP: {rdn}")
            return len(self.dst.find(rdn))

        def check_object(rdn, expected_count=None):
            """ Check for LDAP rdn entry
            return object if found, raise assertion if not
            """

            logger.info(f"*** Checking LDAP: {rdn}")

            r = self.dst.find(rdn)

            if expected_count:
                self.assertEqual(len(r), expected_count)

            if not r:
                logger.error("No results for: {}".format(rdn))

            logger.debug("Result: {}".format(r))

            self.assertTrue(bool(r))
            return r

        def check_people(rdn, people, context_checks):
            """ Check that people object exists and that users exists
            """
            check_object(rdn)

            for u in people:
                # Suspended users don't appear in LDAP
                if u['user'].get('suspended') is True:
                    continue

                user_object = check_object(f"uid={u['user']['username']},{rdn}")

                # Specify as much of tests to see that all LDAP entries are correct

                # Example: verify that ssh Public key and objectClass is present
                # when SBS user profile has ssh_keys...
                if u['user'].get('ssh_keys', None):
                    self.assertTrue('ldapPublicKey' in user_object[list(user_object)[0]]['objectClass'])
                    self.assertTrue('sshPublicKey' in user_object[list(user_object)[0]].keys())

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
                # logger.debug(f"member: {m['user']['username']}, status: {m['status']}")
                logger.debug(f"member: {m['user']['username']}")
                # if m['status'] == 'active' and m['user'].get('suspended') is not True:
                active_members.append(m)

            if len(active_members) > 0:
                member_element = group_object[list(group_object)[0]]['member']

                for m in member_element:
                    logger.debug(f"Found member: {m}")

                found_members = [m.split(',')[0].split('=')[1] for m in member_element]
                required_members = [m['user']['username'] for m in active_members]

                self.assertEqual(sorted(found_members), sorted(required_members))

        def check_ldap(rdn, people, groups, group_name_function, context_checks=[]):
            """ check for ordered object entry and check both people and object subtrees
            """
            check_object(rdn)

            check_people(f"ou=people,{rdn}", people, context_checks)
            if len(people) > 0:
                check_group(f"ou=groups,{rdn}", group_name_function("@all"), people)

            for g in groups:
                check_group(f"ou=groups,{rdn}", group_name_function(g['short_name']), g['collaboration_memberships'])

        services = self.src.service_collaborations()

        for s_id, s in services.items():
            logger.info(f"* checking service: {s_id}")

            for co_id, c in s.get('cos', {}).items():
                logger.info(f"* Checking collaboration: {c['name']}")

                # detail = self.src.collaboration(c['id'])
                # detail = cos(c['id'])
                # for s_id, s in services.items():

                def check_ordered_person_expiry(person, _):
                    # When CO is expired, the person in de Ordered Subtree should mut be expired as well
                    if c['status'] == 'expired':
                        logger.debug(f"Checking expiry status of {person['user']['username']}")
                        self.assertEqual(person['status'], 'expired')

                def check_accepted_policy_agreement(person, person_object):
                    # Verify that AUP attribute exists when accepted by user for this service
                    # and not exists when not (yet) accepted by the user...

                    username = person['user']['username']

                    aup_found = False

                    for u in self.users:
                        if u['username'] == username:
                            self.assertTrue('accepted_aups' in u)

                            for aup in u['accepted_aups']:
                                self.assertTrue('service_id' in aup)

                                if aup['service_id'] == s_id:
                                    aup_found = True
                                    break

                            break

                    policy_agreement_attribute = False

                    for a in person_object[list(person_object)[0]]:
                        if a.startswith('voPersonPolicyAgreement'):
                            policy_agreement_attribute = True
                            break

                    if policy_agreement_attribute:
                        self.assertTrue(aup_found)
                    else:
                        self.assertFalse(aup_found)

                org_sname = c['organisation']['short_name']

                def group_name_ordered(g):
                    return g

                def group_name_flat(g):
                    return f"{org_sname}.{c['short_name']}.{g}"

                logger.info(f"** Checking Service: {s_id}, Enabled: {s['enabled']}")

                if s['enabled']:
                    check_ldap(
                        f"o={org_sname}.{c['short_name']},dc=ordered,dc={s_id},\
                        {self.dst_conf['basedn']}",
                        c['collaboration_memberships'],
                        c['groups'],
                        group_name_ordered,
                        context_checks=[
                            check_ordered_person_expiry,
                            check_accepted_policy_agreement
                        ]
                    )

                    check_ldap(
                        f"dc=flat,dc={s_id},{self.dst_conf['basedn']}",
                        c['collaboration_memberships'],
                        c['groups'],
                        group_name_flat
                    )
                elif object_count(f"dc={s_id},{self.dst_conf['basedn']}") > 0:
                    # in case the service 'exists' in LDAP but is not enabled, make sure
                    # people and group are 'empty'
                    check_ldap(
                        f"o={org_sname}.{c['short_name']},dc=ordered,dc={s_id},\
                        {self.dst_conf['basedn']}",
                        [],
                        [],
                        group_name_ordered
                    )
                    check_ldap(
                        f"dc=flat,dc={s_id},{self.dst_conf['basedn']}",
                        [],
                        [],
                        group_name_flat
                    )

                if object_count(f"dc={s_id},{self.dst_conf['basedn']}") > 0:
                    logger.info(f"*** Checking Admin account: {s_id}")
                    self.assertTrue('ldap_password' in s)
                    admin_object = check_object(f"cn=admin,dc={s_id},"
                                                f"{self.dst_conf['basedn']}", expected_count=1)
                    ldap_password = s['ldap_password']
                    if ldap_password:
                        userPassword = admin_object[list(admin_object)[0]]['userPassword']
                        self.assertEqual(userPassword, ['{CRYPT}' + ldap_password])
