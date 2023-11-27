#!/usr/bin/env python3

import sys
import yaml
import copy
import ldap
import os
import util
import logging
import uuid
import datetime

from sldap import SLdap
from sbs import SBS

from typing import Tuple, List, Dict, Union, Optional

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

SBSPerson = Dict[str, str]
LDAPEntry = Dict[str, List[Union[str, int]]]

# vc keeps track of visited CO's, so we can delete what
# we have not seen in the Cleanup phase
vc = {}


def add_scope(scope: str, sep: str = '.', values: Optional[List[str]] = None) -> Optional[List[str]]:
    if values is None:
        return None
    return set(f"{scope}{sep}{v}" for v in values)


# Here's the magic: Build the new person entry
def sbs2ldap_record(sbs_uid: str, sbs_user: SBSPerson) -> Tuple[str, LDAPEntry]:
    record: LDAPEntry = dict(
        objectClass=['inetOrgPerson', 'person', 'eduPerson', 'voPerson']
    )

    record['eduPersonUniqueId'] = [sbs_uid]

    record['displayName'] = [sbs_user.get('name') or 'n/a']
    record['givenName'] = [sbs_user.get('given_name') or 'n/a']
    record['sn'] = [sbs_user.get('family_name') or 'n/a']
    # cn is required in the posixAccount schema, otherwise we wouldn't use it
    record['cn'] = [sbs_uid]

    record['mail'] = [sbs_user.get('email')]

    # affiliation
    scoped_affiliation = sbs_user.get('scoped_affiliation')
    if scoped_affiliation:
        record['voPersonExternalAffiliation'] = [v.strip() for v in sbs_user.get('scoped_affiliation').split(',')]
    else:
        record['voPersonExternalAffiliation'] = []
    # TODO: fix this hack. ePSA is not stored in SBS, but as it is always fixed, we can hardcode it here
    record['eduPersonScopedAffiliation'] = ['member@sram.surf.nl']

    # principal name
    record['voPersonExternalID'] = [sbs_user.get('eduperson_principal_name')]
    # TODO: expose this in SBS
    #record['eduPersonPrincipalName'] = ['bla']

    # posixAccount
    username = sbs_user.get('username')

    record['uid'] = [username]
    if sbs_user.get('ssh_keys') or sbs_user.get('ssh_keys'):
        sshkeys = [sbs_user.get('ssh_key')] if 'ssh_key' in sbs_user else sbs_user.get('ssh_keys')
        record['sshPublicKey'] = list(set(sshkeys))
        record['objectClass'].append('ldapPublicKey')

    record['voPersonStatus'] = [sbs_user.get('status', 'undefined')]

    # clean up the lists, such that we return empty lists if no attribute is present, rather than [None]
    for key, val in record.items():
        record[key] = list(filter(None, record[key]))

    rdn = f"uid={username}"

    return rdn, record


registered_users = []


# Create phase
def create(src, dst):
    global vc
    global registered_users

    logging.debug("=== slp-ordered ====")

    registered_users = []

    # Find all CO's in SBS
    collaborations = src.service_collaborations()

    logging.debug("--- Create ---")
    for service, details in collaborations.items():
        vc[service] = {}

        cos = details['cos']
        service_id = details['service_id']

        logging.debug("service: {}".format(service))

        # check if service exists and create it if necessary
        service_dn = f"dc={service},{dst.basedn}"
        admin_dn = 'cn=admin,' + service_dn

        # find existing services
        service_dns = dst.find(dst.basedn, f"(&(objectClass=dcObject)(dc={service}))")

        # Pivotal 106: If Service does not (yet) exists in LDAP and is not enable for LDAP
        # in SBS, do not create it at all. If it does exists in LDAP, that means that
        # it has been enabled beforem, and now it is disabled in SBS, then clean
        # people & group entries, but leave structure in place !
        # That situation is handled later below...
        if len(service_dns) == 0 and not details['enabled']:
            continue

        # Define service entry
        service_entry = {
            'objectClass': ['dcObject', 'organization', 'extensibleObject'],
            'dc': [service],
            'o': [service],
            'name': [details['abbreviation']],
            'displayName': [details['name']],
        }
        aup = details['aup']
        pp = details['pp']
        if aup or pp:
            service_entry['objectClass'].append('labeledURIObject')
        if aup:
            service_entry.setdefault('labeledURI', []).append(f"{aup} aup")
        if pp:
            service_entry.setdefault('labeledURI', []).append(f"{pp} pp")

        if len(service_dns) == 0:  # no existing service found
            dst.add(service_dn, service_entry)

            # Initialize with admin object
            admin_entry = {
                'objectClass': ['organizationalRole', 'simpleSecurityObject'],
                'cn': ['admin'],
                'userPassword': [str(uuid.uuid4())]
            }
            dst.add(admin_dn, admin_entry)

            #seq_dn = 'ou=Sequence,' + service_dn
            #seq_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': ['Sequence']}
            #dst.add(seq_dn, seq_entry)

            #uid_dn = 'cn=uidNumberSequence,ou=Sequence,' + service_dn
            #uid_entry = {'objectClass': ['top', 'device'], 'serialNumber': [config['uid']]}
            #dst.add(uid_dn, uid_entry)

            #gid_dn = 'cn=gidNumberSequence,ou=Sequence,' + service_dn
            #gid_entry = {'objectClass': ['top', 'device'], 'serialNumber': [config['gid']]}
            #dst.add(gid_dn, gid_entry)
        elif len(service_dns) == 1:
            dst.store(service_dn, service_entry)
        else:
            raise Exception(f"Found multiple dns for service {service}")

        # Adjust admin userPassword with ldap_password if given in SBS.
        # https://github.com/SURFscz/plsc/issues/24
        if 'ldap_password' not in details:
            raise Exception('ldap_password not found')
        ldap_password = details['ldap_password']
        current_admin = dst.find(admin_dn, "(&(objectClass=simpleSecurityObject)(cn=admin))")
        if ldap_password is None:
            # Effectively disable password
            ldap_password = '!'
        new_admin = {
            'objectClass': ['organizationalRole', 'simpleSecurityObject'],
            'cn': ['admin'],
            'userPassword': ["{CRYPT}" + ldap_password]
        }
        dst.modify(admin_dn, list(current_admin.values())[0], new_admin)

        # check if dc=ordered subtree exists and create it if necessary
        ordered_dns = dst.rfind(f"dc={service}", "(&(objectClass=dcObject)(dc=ordered))")
        if len(ordered_dns) == 0:
            ordered_dn = f"dc=ordered,dc={service},{dst.basedn}"
            ordered_entry = {'objectClass': ['dcObject', 'organizationalUnit'], 'dc': ['ordered'], 'ou': ['ordered']}
            dst.store(ordered_dn, ordered_entry)

        # iterate over all COs that are connected to this service
        for co_id, co in cos.items():
            if 'short_name' not in co or 'short_name' not in co['organisation']:
                raise Exception(f"Encountered CO without short_name: {co}")
            # TODO: rename this to co_urn
            co_identifier = "{}.{}".format(co['organisation']['short_name'], co['short_name'])

            logging.debug("- co: {}/{}".format(co_id, co_identifier))
            vc[service][co_identifier] = {}
            vc[service][co_identifier]['roles'] = {}
            vc[service][co_identifier]['members'] = []
            vc[service][co_identifier]['name'] = co.get('name', co_identifier)
            vc[service][co_identifier]['tags'] = add_scope(values=co.get('tags'),
                                                           scope=co['organisation']['short_name'])

            # Create CO if necessary
            co_dn = f"o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
            co_entry = {
                'objectClass': ['top', 'organization', 'extensibleObject'],
                'o': [co_identifier],
                'uniqueIdentifier': [co['identifier']]
            }

            # Add labeledURI attribute...
            for labeledURI in ['sbs_url', 'logo']:
                if labeledURI in co and co[labeledURI]:
                    co_entry.setdefault('labeledURI', []).append(
                        co[labeledURI].strip().replace(' ', '%20') + " " + labeledURI
                    )

            if co.get('description'):
                co_entry['description'] = [co.get('description')]
            if co.get('name'):
                co_entry['displayName'] = [co.get('name')]
            if co.get('tags'):
                co_entry['businessCategory'] = add_scope(values=co.get('tags'),
                                                         scope=co['organisation']['short_name'])
            co_entry['mail'] = list(set(admin.get('email') for admin in co.get('admins')))

            co_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=organization)(o={co_identifier}))")

            if details['enabled']:
                logging.debug("- Enabled")
                if len(co_dns) == 0:
                    dst.add(co_dn, co_entry)
                    for ou in ['Groups', 'People']:
                        ou_dn = 'ou=' + ou + ',' + co_dn
                        ou_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': [ou]}
                        dst.add(ou_dn, ou_entry)
                elif len(co_dns) == 1:
                    current_entry = list(co_dns.values())[0]
                    dst.modify(co_dn, current_entry, co_entry)
                else:
                    raise Exception(f"Found multiple COs for o={co_identifier}")
            else:
                logging.debug("- Disabled")
                if len(co_dns):
                    # Pivotal 106: If not 'ldap_enabled' do not populate actual people / groups
                    # This is case when this service has been provisioned earlier, but now is
                    # disable in SBS, just stop populating any further !
                    for co_dn in co_dns:
                        dst.rdelete(co_dn)
                continue

            users = src.users(co)
            # logging.debug(f"users: {users}")

            logging.debug("  - All groups")
            groups = src.groups(co)
            #logging.debug(f"groups: {groups}")
            for gid, group in groups.items():
                grp_id = group['identifier']
                grp_name = group['short_name']
                # global_urn isn't always filled, so fall back to generating it ourselves
                grp_urn = group.get('global_urn') or f"{co_identifier}:{grp_name}"
                # use . instead of : to make the group names safe to use in *nix
                grp_urn.replace(':', '.')

                logging.debug("      - grp: {}/{}".format(group['id'], grp_urn))
                vc[service][co_identifier].setdefault('groups', []).append(grp_name)

                grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
                grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}",
                                    f"(&(objectClass=groupOfMembers)(cn={grp_name}))")
                if len(grp_dns) == 1:
                    old_dn, old_entry = list(grp_dns.items())[0]
                    #gidNumber = old_entry.get('gidNumber', [None])[0]
                    members = old_entry.get('member', [])
                elif len(grp_dns) == 0:
                    members = []
                else:
                    raise Exception(f"Found multiple groups for dn={grp_dn}")

                #if not gidNumber:
                #    gidNumber = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")

                # Here's the magic: Build the new group entry
                grp_entry = {
                    'objectClass': ['extensibleObject', 'groupOfMembers'],
                    'cn': [grp_name],
                    'uniqueIdentifier': [grp_id],
                    #'labeledURI': [grp_urn],
                    #'gidNumber': [gidNumber],
                    'member': members
                }
                if group.get('description'):
                    grp_entry['description'] = [group.get('description')]
                if group.get('name'):
                    grp_entry['displayName'] = [group.get('name')]

                # TODO: Why are we always updating?  Shouldn't this be conditional on an actual change happening?
                # if grp_entry != old_entry:
                ldif = dst.store(grp_dn, grp_entry)
                logging.debug("      - store: {}".format(ldif))

            logging.debug("  - People")

            for src_id, src_detail in users.items():
                # logging.debug(f"user: {src_detail}")
                src_user = src_detail['user']
                logging.debug("    - src_id: {}/{}".format(src_id, src_user['uid']))
                src_uid = util.uid(src_user)
                logging.debug("    - src_uid: {}/{}".format(src_id, src_uid))

                # convert the BS data to an LDAP record
                dst_rdn, dst_entry = sbs2ldap_record(src_uid, src_user)
                dst_dn = f"{dst_rdn},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"

                # Pivotal #181218689
                accepted_aups = src_user.get("accepted_aups", [])
                for aup in accepted_aups:
                    if aup.get("service_id", -1) == service_id:

                        agreed_at = datetime.datetime.strptime(aup['agreed_at'] + "+0000", '%Y-%m-%d %H:%M:%S%z')

                        dst_entry['voPersonPolicyAgreement;time-{}'.format(
                            int(datetime.datetime.timestamp(agreed_at))
                        )] = [aup['url']]

                registered_users.append(dst_dn)

                try:
                    ldif = dst.store(dst_dn, dst_entry)
                    logging.debug(f"      - store {dst_dn}: {ldif}")
                except ldap.OBJECT_CLASS_VIOLATION as e:
                    logging.error(f"Error creating LDIF: {str(e)} for {dst_dn}")
                    continue

                # record user as CO member
                vc[service][co_identifier]['members'].append(src_uid)

                # Pivotal #180730988
                if dst_entry['voPersonStatus'][0] == 'expired':
                    logging.debug(f"User {dst_rdn} is not participating in any group because of expiration !")
                    continue

                # handle groups
                logging.debug("    - Groups")
                for group in src_detail['groups']:
                    grp_id = group['identifier']
                    grp_name = group['short_name']
                    # global_urn isn't always filled, so fall back to generating it ourselves
                    grp_urn = group.get('global_urn') or f"{co_identifier}:{grp_name}"
                    # use . instead of : to make the group names safe to use in *nix
                    grp_urn.replace(':', '.')

                    logging.debug("      - grp: {}/{}".format(group['id'], grp_urn))

                    # TODO: what does this do, exactly?  Can't we simplify this?
                    vc[service][co_identifier]['roles'].setdefault(grp_id, []).append(dst_dn)
                    #vc[service][co_identifier].setdefault('groups', []).append(grp_urn)
                    vc[service][co_identifier].setdefault('groups', []).append(grp_name)

                    grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
                    grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}",
                                        f"(&(objectClass=groupOfMembers)(cn={grp_name}))")

                    # ipdb.set_trace()
                    if len(grp_dns) == 1:
                        old_dn, old_entry = list(grp_dns.items())[0]
                        members = old_entry.get('member', [])
                        if dst_dn not in members:
                            members.append(dst_dn)
                    elif len(grp_dns) == 0:
                        members = [dst_dn]
                    else:
                        raise Exception("Too many DNs, this shouldn't happen")

                    # Here's the magic: Build the new group entry
                    grp_entry = {
                        'objectClass': ['extensibleObject', 'groupOfMembers'],
                        'cn': [grp_name],
                        'uniqueIdentifier': [grp_id],
                        #'labeledURI': [grp_urn],
                        #'gidNumber': [gidNumber],
                        'member': members
                    }
                    if group.get('description'):
                        grp_entry['description'] = [group.get('description')]
                    if group.get('name'):
                        grp_entry['displayName'] = [group.get('name')]

                    # TODO: Why are we always updating?  Shouldn't this be conditional on an actual change happening?
                    ldif = dst.store(grp_dn, grp_entry)
                    logging.debug("      - store: {}".format(ldif))

            if details['enabled']:
                logging.debug("  - Group all")
                # global_urn isn't always filled, so fall back to generating it ourselves
                grp_name = "@all"
                grp_id = co['identifier']

                logging.debug("      - grp: {}".format(grp_name))
                vc[service][co_identifier].setdefault('groups', []).append(grp_name)

                grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"

                members = []
                for src_id, src_detail in users.items():
                    src_user = src_detail['user']
                    src_uid = util.uid(src_user)
                    dst_rdn, dst_entry = sbs2ldap_record(src_uid, src_user)

                    # Pivotal #180730988
                    if dst_entry['voPersonStatus'][0] == 'expired':
                        logging.debug(f"User {dst_rdn} is not participating @ALL group because of expiration !")
                        continue

                    dst_dn = f"{dst_rdn},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
                    members.append(dst_dn)
                    vc[service][co_identifier]['roles'].setdefault(grp_id, []).append(dst_dn)

                #if not gidNumber:
                #    gidNumber = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")

                # Here's the magic: Build the new group entry
                grp_entry = {
                    'objectClass': ['extensibleObject', 'groupOfMembers'],
                    'cn': [grp_name],
                    'uniqueIdentifier': [grp_id],
                    #'labeledURI': [grp_urn],
                    #'gidNumber': [gidNumber],
                    'member': members,
                    'description': ['All CO members'],
                    'displayName': [f'All Members of {vc[service][co_identifier]["name"]}']
                }

                # Add tags
                if vc[service][co_identifier]["tags"]:
                    grp_entry['businessCategory'] = vc[service][co_identifier]["tags"]

                # Add labeledURI
                for labeledURI in ['sbs_url', 'logo']:
                    if labeledURI in co and co[labeledURI]:
                        grp_entry.setdefault('labeledURI', []).append(
                            co[labeledURI].strip().replace(' ', '%20') + " " + labeledURI
                        )

                ldif = dst.store(grp_dn, grp_entry)
                logging.debug("      - store: {}".format(ldif))


# Cleanup phase
def cleanup(dst):
    global vc
    global registered_users

    logging.debug("-- Cleanup ---")
    service_dns = dst.find(f"{dst.basedn}", "(&(objectClass=organization))", scope=ldap.SCOPE_ONELEVEL)
    for service_dn, s in service_dns.items():
        service = s['dc'][0]
        logging.debug(f"service: {service}")
        if vc.get(service, None) is None:
            logging.debug(f"- {service} not found in our services, cleaning up")
            dst.rdelete(f"{service_dn}")
            continue

        organizations = dst.rfind(f"dc=ordered,dc={service}",
                                  '(&(objectClass=organization)(objectClass=extensibleObject))')
        for o_dn, o_entry in organizations.items():
            if o_entry.get('o'):
                o_rdns = util.dn2rdns(o_dn)
                co = o_rdns['o'][0]
                dc = o_rdns['dc'][1]

                logging.debug(f"  - CO: {co}")
                logging.debug(f"    - dest_dn: {o_dn}")
                if vc[service].get(co) is None:
                    logging.debug(f"   - {co} not found in our services, deleting")
                    dst.rdelete(o_dn)
                    continue

                logging.debug("  - People")
                src_members = vc.get(dc, {}).get(co, {}).get('members', [])
                dst_dns = dst.rfind("ou=people,o={},dc=ordered,dc={}".format(co, service), '(objectClass=person)')
                for dst_dn, dst_entry in dst_dns.items():
                    logging.debug("    - dest_dn: {}".format(dst_dn))
                    if dst_entry.get('eduPersonUniqueId', None):
                        dst_uid = dst_entry['eduPersonUniqueId'][0]
                        if dst_uid not in src_members:
                            logging.debug("      dst_uid not found in src_members, deleting {}".format(dst_dn))
                            dst.delete(dst_dn)
                        else:
                            # verify that rdn uid is indeed (still) valid registered user, if not delete entry
                            if dst_dn not in registered_users:
                                dst.delete(dst_dn)

                logging.debug("  - Groups")
                dst_dns = dst.rfind("ou=Groups,o={},dc=ordered,dc={}".format(co, service),
                                    '(objectClass=groupOfMembers)')
                for dst_dn, dst_entry in dst_dns.items():
                    grp_name = dst_entry['cn'][0]
                    if grp_name not in vc.get(dc, {}).get(co, {}).get('groups', []):
                        logging.debug(f"        {grp_name} not found, deleting {dst_dn}")
                        dst.delete(dst_dn)
                        continue

                    #grp_urn = dst_entry['labeledURI'][0]
                    logging.debug("    - dest_dn: {}".format(dst_dn))
                    # TODO: rework this to use the short_name uri-like cn attribute instead of the sbs id
                    src_id = dst_entry.get('uniqueIdentifier')
                    if src_id is None:
                        logging.debug("        sbs identifier not found, deleting {}".format(dst_dn))
                        dst.delete(dst_dn)
                    else:
                        new_entry = copy.deepcopy(dst_entry)
                        src_id = src_id[0]
                        dst_members = new_entry.get('member', [])
                        #src_members = vc.get(dc, {}).get(co, {}).get('roles', {}).get(int(src_id), [])
                        src_members = vc.get(dc, {}).get(co, {}).get('roles', {}).get(src_id, [])
                        removed = False  # TODO: rename this to is_modified
                        # ipdb.set_trace()
                        for dst_member in dst_members:
                            dst_rdn = util.dn2rdns(dst_member)["uid"][0]
                            #dst_rdn = util.dn2rdns(dst_member)['cn'][0]
                            logging.debug("      - dst_member: {}".format(dst_rdn))
                            if dst_member not in src_members:
                                logging.debug("        dst_member not found, deleting {}".format(dst_rdn))
                                dst_members.remove(dst_member)
                                removed = True
                        if removed:
                            dst.modify(dst_dn, dst_entry, new_entry)


def main():
    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = SBS(config['sbs']['src'])
    dst = SLdap(config['ldap']['dst'])

    create(src, dst)
    cleanup(dst)


if __name__ == "__main__":
    main()
