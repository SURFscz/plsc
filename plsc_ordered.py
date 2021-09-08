#!/usr/bin/env python3

import sys
import yaml
import copy
import ldap
import datetime
import os
import util
import logging
import uuid

from sldap import sLDAP
from sbs import SBS

from typing import Tuple, List, Dict, Union

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

SBSPerson = Dict[str, str]
LDAPEntry = Dict[str, List[Union[str, int]]]

# vc keeps track of visited CO's so we can delete what
# we have not seen in the Cleanup phase
vc = {}


# Here's the magic: Build the new person entry
def sbs2ldap_record(sbs_uid: str, sbs_user: SBSPerson) -> Tuple[str, LDAPEntry]:
    record: LDAPEntry = dict(
        objectClass=['inetOrgPerson', 'person', 'eduPerson', 'voPerson', 'loginProperties']
    )

    record['eduPersonUniqueId'] = [sbs_uid]

    record['displayName'] = [sbs_user.get('name') or 'n/a']
    record['givenName'] = [sbs_user.get('given_name') or 'n/a']
    record['sn'] = [sbs_user.get('family_name') or 'n/a']
    # cn is required in the posixAccount schema, otherwise we wouldn't use it
    record['cn'] = [sbs_uid]

    record['mail'] = [sbs_user.get('email')]

    # affiliation
    record['voPersonExternalAffiliation'] = [sbs_user.get('scoped_affiliation')]
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
        record['sshPublicKey'] = [sbs_user.get('ssh_key')] if 'ssh_key' in sbs_user else sbs_user.get('ssh_keys')
        record['objectClass'].append('ldapPublicKey')

    # Implement loginTime info. For privacy reasons the last login time is aggregated to a date
    # as in below formula. (see Pivotal https://www.pivotaltracker.com/n/projects/2230595/stories/178707465)

    last_login_date = datetime.datetime.strptime(sbs_user.get('last_login_date'), "%Y-%m-%d %H:%M:%S")
    delta = datetime.datetime.now() - last_login_date

    logging.debug(f"LAST LOGIN: {last_login_date.strftime('%Y-%m-%d')}, DELTA: {delta.days} days")

    if delta.days <= 2:
        last_login_date = datetime.datetime.today()
    elif delta.days <= 7:
        last_login_date = datetime.datetime.today() - datetime.timedelta(days=1)
    elif delta.days <= 30:
        last_login_date = datetime.datetime.today() - datetime.timedelta(days=7)
    elif delta.days <= 90:
        last_login_date = datetime.datetime.today() - datetime.timedelta(days=30)
    else:
        last_login_date.replace(day=1)

    logging.debug("LAST LOGIN RESULT: {}".format(last_login_date.strftime("%Y-%m-%d")))

    record['loginTime'] = [last_login_date.strftime("%Y%m%d0000Z")]

    if sbs_user.get('status', 'active') == 'expired':
        record['loginDisabled'] = ['TRUE']
    else:
        record['loginDisabled'] = ['FALSE']

    # clean up the lists, such that we return empty lists if no attribute it present, rather than [None]
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
    for service, cos in collaborations.items():
        vc[service] = {}

        logging.debug("service: {}".format(service))

        # check if service exists and create it if necessary
        service_dn = f"dc={service},{dst.basedn}"

        # find existing services
        service_dns = dst.find(dst.basedn, f"(&(objectClass=dcObject)(dc={service}))")
        if len(service_dns) == 0:  # no existing service found
            service_entry = {'objectClass': ['dcObject', 'organization'], 'dc': [service], 'o': [service]}
            dst.add(service_dn, service_entry)

            admin_dn = 'cn=admin,' + service_dn
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

            # Skip unknown CO's
            organizations = dst.rfind(f"dc=ordered,dc={service}",
                                      f"(&(objectClass=organization)(objectClass=extensibleObject)(o={co_identifier}))")
            if len(organizations):
                o_dn, o_entry = list(organizations.items())[0]

            # Create CO if necessary
            co_dn = f"o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
            co_entry = {
                'objectClass': ['top', 'organization', 'extensibleObject'],
                'o': [co_identifier],
                #'uniqueIdentifier': [co_id],
                'uniqueIdentifier': [co['identifier']],
                #'labeledURI': [co_identifier]
            }
            if co.get('description'):
                co_entry['description'] = [co.get('description')]
            if co.get('name'):
                co_entry['displayName'] = [co.get('name')]

            co_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=organization)(o={co_identifier}))")
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

                # convert the BS data to an ldap record
                dst_rdn, dst_entry = sbs2ldap_record(src_uid, src_user)
                dst_dn = f"{dst_rdn},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"

                registered_users.append(dst_dn)

                # add the uidNumber and gidNumber
                #uidNumber = None
                #gidNumber = None
                dst_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(ObjectClass=person)(eduPersonUniqueId={src_uid}))")
                if dst_dns:
                    old_dn, old_entry = list(dst_dns.items())[0]
                    #uidNumber = old_entry.get('uidNumber', 0)[0]
                    #gidNumber = old_entry.get('gidNumber', 0)[0]

                #if uidNumber is None:
                #    uidNumber = dst.get_sequence(f"cn=uidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
                #if gidNumber is None:
                #    gidNumber = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")

                #dst_entry['uidNumber'] = [uidNumber]
                #dst_entry['gidNumber'] = [gidNumber]

                try:
                    ldif = dst.store(dst_dn, dst_entry)
                    logging.debug(f"      - store {dst_dn}: {ldif}")
                except ldap.OBJECT_CLASS_VIOLATION as e:
                    logging.error(f"Error creating LDIF: {str(e)} for {dst_dn}")
                    continue

                # record user as CO member
                vc[service][co_identifier]['members'].append(src_uid)

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
                        #gidNumber = old_entry.get('gidNumber', [None])[0]
                        members = old_entry.get('member', [])
                        if dst_dn not in members:
                            members.append(dst_dn)
                    elif len(grp_dns) == 0:
                        members = [dst_dn]
                    else:
                        raise Exception("Too many dn's, this shouldn't happen")

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

            if True:
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
            logging.debug(f"- {service} not found in our services, deleting")
            # service_dn = f"dc={service},{dst.basedn}"
            dst.rdelete(service_dn)

        organizations = dst.rfind(f"dc=ordered,dc={service}",
                                  '(&(objectClass=organization)(objectClass=extensibleObject))')
        for o_dn, o_entry in organizations.items():
            if o_entry.get('o'):
                o_rdns = util.dn2rdns(o_dn)
                co = o_rdns['o'][0]
                dc = o_rdns['dc'][1]

                logging.debug("  - People")
                src_members = vc.get(dc, {}).get(co, {}).get('members', [])
                dst_dns = dst.rfind("ou=people,o={},dc=ordered,dc={}".format(co, service), '(objectClass=person)')
                for dst_dn, dst_entry in dst_dns.items():
                    logging.debug("    - dstdn: {}".format(dst_dn))
                    if dst_entry.get('eduPersonUniqueId', None):
                        dst_uid = dst_entry['eduPersonUniqueId'][0]
                        if dst_uid not in src_members:
                            logging.debug("      dst_uid not found in src_members, deleting {}".format(dst_dn))
                            dst.delete(dst_dn)
                        else:
                            # verify that rdn uid is indeed (stil) valid registered user, if not delete entry
                            if dst_dn not in registered_users:
                                dst.delete(dst_dn)

                logging.debug("  - Groups")
                dst_dns = dst.rfind(f"ou=Groups,o={co},dc=ordered,dc={service}", '(objectClass=groupOfMembers)')
                for dst_dn, dst_entry in dst_dns.items():
                    grp_name = dst_entry['cn'][0]
                    #grp_urn = dst_entry['labeledURI'][0]
                    logging.debug("    - dstdn: {}".format(dst_dn))
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
                        if grp_name not in vc.get(dc, {}).get(co, {}).get('groups', []):
                            logging.debug(f"        {grp_name} not found, deleting {dst_dn}")
                            dst.delete(dst_dn)

                logging.debug("  - CO")
                logging.debug(f"    - dstdn: {o_dn}")
                if vc[service].get(co) is None:
                    logging.debug(f"   - {co} not found in our services, deleting")
                    dst.rdelete(o_dn)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = SBS(config['sbs']['src'])
    dst = sLDAP(config['ldap']['dst'])

    create(src, dst)
    cleanup(dst)
