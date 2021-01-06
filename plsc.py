#!/usr/bin/env python3

import sys
import yaml
import re
import socket

import util
from sldap import sLDAP

#import ipdb
#ipdb.set_trace()

if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

src = sLDAP(config['ldap']['src'])
dst = sLDAP(config['ldap']['dst'])
fqdn = socket.getfqdn() + ':plsc'

services = util.find_services(src)
collaborations = util.find_collaborations(src, services)

# Create phase
def create():
    print("--- Create ---")
    for service, cos in collaborations.items():
        print("service: {}".format(service))

        # Create service if necessary
        service_dn = f"dc={service},{dst.basedn}"
        service_dns = dst.find(dst.basedn, f"(&(objectClass=dcObject)(dc={service}))")
        if len(service_dns) == 0:
            service_entry = {'objectClass': ['dcObject', 'organization'], 'dc': [service], 'o': [service]}
            dst.add(service_dn, service_entry)
            admin_dn = 'cn=admin,' + service_dn
            admin_entry = {'objectClass': ['organizationalRole', 'simpleSecurityObject'], 'cn': ['admin'],
                        'userPassword': [config['pwd']]}
            dst.add(admin_dn, admin_entry)
            seq_dn = 'ou=Sequence,' + service_dn
            seq_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': ['Sequence']}
            dst.add(seq_dn, seq_entry)
            uid_dn = 'cn=uidNumberSequence,ou=Sequence,' + service_dn
            uid_entry = {'objectClass': ['top', 'device'], 'serialNumber': [config['uid']]}
            dst.add(uid_dn, uid_entry)
            gid_dn = 'cn=gidNumberSequence,ou=Sequence,' + service_dn
            gid_entry = {'objectClass': ['top', 'device'], 'serialNumber': [config['gid']]}
            dst.add(gid_dn, gid_entry)

        # Ordered dn
        ordered_dns = dst.rfind(f"dc={service}", "(&(objectClass=dcObject)(dc=ordered))")
        if len(ordered_dns) == 0:
            ordered_dn = f"dc=ordered,dc={service},{dst.basedn}"
            ordered_entry = {'objectClass': ['dcObject', 'organization'], 'dc': ['ordered'], 'o': [service]}
            dst.add(ordered_dn, ordered_entry)

        for co_name, co_id in cos:
            co_id = co_id[0]
            print("- co: {}/{}".format(co_name, co_id))

            # Skip unknown CO's
            organizations = dst.rfind("o={},dc=ordered,dc={}".format(co_id, service),
                                    '(&(objectClass=organization)(objectClass=extensibleObject))')
            if len(organizations):
                o_dn, o_entry = list(organizations.items())[0]
                co_fqdn = o_entry.get('host', [])
                if fqdn not in co_fqdn:
                    print("skipping {}".format(co_fqdn))
                    continue

            # Create CO if necessary
            co_dn = f"o={co_id},dc=ordered,dc={service},{dst.basedn}"
            co_entry = {'objectClass': ['top', 'organization', 'extensibleObject'], 'o': [co_id], 'description': [co_name],
                        'host': [fqdn]}
            co_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=organization)(o={co_id}))")
            if len(co_dns) == 0:
                dst.add(co_dn, co_entry)
                for ou in ['Groups', 'People']:
                    ou_dn = 'ou=' + ou + ',' + co_dn
                    ou_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': [ou]}
                    dst.add(ou_dn, ou_entry)

            print("  People")
            src_dns = src.rfind("ou=People,o={}".format(co_name), '(ObjectClass=person)')

            for src_dn, src_entry in src_dns.items():
                print("  - srcdn: {}".format(src_dn))
                src_uid = src_entry['uid'][0]

                dst_dn = f"uid={src_uid},ou=People,o={co_id},dc=ordered,dc={service},{dst.basedn}"
                dst_dns = dst.rfind("dc=ordered,dc={}".format(service), "(&(ObjectClass=person)(uid={}))".format(src_uid))

                dst_entry = {'objectClass': ['inetOrgPerson', 'person', 'posixAccount']}

                # ipdb.set_trace()

                if len(dst_dns) >= 1:
                    old_dn, old_entry = list(dst_dns.items())[0]
                    dst_entry['uidNumber'] = old_entry.get('uidNumber', 0)
                    dst_entry['gidNumber'] = old_entry.get('gidNumber', 0)
                elif len(dst_dns) == 0:
                    uid = dst.get_sequence(f"cn=uidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
                    dst_entry['uidNumber'] = [uid]
                    gid = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
                    dst_entry['gidNumber'] = [gid]

                # Here's the magic: Build the new person entry
                dst_entry['uid'] = [src_uid]
                dst_entry['cn'] = src_entry.get('cn', [])
                dst_entry['sn'] = src_entry.get('sn', [])
                dst_entry['mail'] = src_entry.get('mail', [])
                dst_entry['homeDirectory'] = ['/home/{}'.format(src_uid)]

                eduPersonPrincipalName = src_entry.get('eduPersonPrincipalName', [])
                if len(eduPersonPrincipalName):
                    dst_entry['objectClass'].append('eduPerson')
                    dst_entry['eduPersonPrincipalName'] = eduPersonPrincipalName

                sshPublicKey = src_entry.get('sshPublicKey', [])
                if len(sshPublicKey):
                    dst_entry['objectClass'].append('ldapPublicKey')
                    dst_entry['sshPublicKey'] = sshPublicKey

                ldif = dst.store(dst_dn, dst_entry)
                print(f"      - store: {ldif}")

            print("  Groups")
            src_dns = src.rfind('ou=Groups,o={}'.format(co_name),
                                '(&(objectClass=groupOfNames)(!(objectClass=labeledURIObject))(!(cn=GRP:CO:*)))')
            for src_dn, src_entry in src_dns.items():
                print("  - srcdn: {}".format(src_dn))
                src_rdns = util.dn2rdns(src_dn)
                src_cn = src_rdns['cn'][0]
                src_type = src_entry['ou'][0]

                # Here's the magic: Build the new group entry
                m = re.search('^(?:GRP)?(?:CO)?(?:COU)?:(.*?)$', src_cn)
                dst_cn = src_type + "_" + m.group(1) if m.group(1) else ""

                dst_entry = {'objectClass': ['extensibleObject', 'posixGroup', 'sczGroup'], 'cn': [dst_cn],
                            'description': [src_cn]}

                members = []

                # Build members
                for member in src_entry['member']:
                    member_rdns = util.dn2rdns(member)
                    # Is member user?
                    dns = []
                    if member_rdns.get('uid', None):
                        dns = dst.rfind("ou=People,o={},dc=ordered,dc={}".format(co_id, service),
                                        "(uid={})".format(member_rdns['uid'][0]))
                    # member is group?
                    elif member_rdns.get('cn', None):
                        dns = dst.rfind("ou=Groups,o={},dc=ordered,dc={}".format(co_id, service),
                                        "(description={})".format(member_rdns['cn'][0]))

                    if len(dns) == 1:
                        member_dst_dn, member_dst_entry = list(dns.items())[0]
                        members.append(member_dst_dn)

                dst_entry['sczMember'] = members

                dst_dns = dst.rfind("ou=Groups,o={},dc=ordered,dc={}".format(co_id, service),
                                    "(&(ObjectClass=posixGroup)(description={}))".format(src_cn))

                if len(dst_dns) == 1:
                    dst_dn, old_entry = list(dst_dns.items())[0]
                    new_entry = old_entry.copy()
                    for attr, values in dst_entry.items():
                        new_entry[attr] = values
                        ldif = dst.modify(dst_dn, old_entry, new_entry)
                        print("    - mod: {}".format(ldif))

                elif len(dst_dns) == 0:
                    gid = dst.get_sequence("cn=gidNumberSequence,ou=Sequence,dc={},{}".format(service, dst.basedn))
                    dst_entry['gidNumber'] = [str(gid)]
                    dst_dn = "cn={},ou=Groups,o={},dc=ordered,dc={},{}".format(dst_cn, co_id, service, dst.basedn)
                    ldif = dst.add(dst_dn, dst_entry)
                    print("    - add: {}".format(ldif))

                else:
                    print("    - Too many dstdn's")

            print()

# Cleanup phase
def cleanup():
    print("--- Cleanup ---")
    for service, cos in collaborations.items():
        print("service: {}".format(service))

        organizations = dst.rfind("dc=ordered,dc={}".format(service),
                                '(&(objectClass=organization)(objectClass=extensibleObject))')
        for o_dn, o_entry in organizations.items():
            # print("o: {}".format(o_dn))
            # print("entry: {}".format(o_entry))

            if o_entry.get('description', None):
                co_name = o_entry['description'][0]
                co_fqdn = o_entry.get('host', [])

                if fqdn not in co_fqdn:
                    print("skipping {}".format(co_fqdn))
                    continue

                o_rdns = util.dn2rdns(o_dn)
                print("- o: {}".format(o_rdns['o'][0]))

                print("  - People")
                dst_dns = dst.rfind("ou=People,o={},dc=ordered,dc={}".format(o_rdns['o'][0], service),
                                    '(objectClass=person)')
                for dst_dn, dst_entry in dst_dns.items():
                    # print("  - dstdn: {}".format(dst_dn))
                    # print("    entry: {}".format(dst_entry))

                    if dst_entry.get('uid', None):
                        src_uid = dst_entry['uid'][0]
                        src_dns = src.rfind("ou=People,o={}".format(co_name), '(uid={})'.format(src_uid))
                        if len(src_dns):
                            for src_dn, src_entry in src_dns.items():
                                pass
                                # print("   - srcdn: {}".format(src_dn))
                        else:
                            print("    - dstdn: {}".format(dst_dn))
                            print("      srcdn not found, deleting {}".format(dst_dn))
                            dst.delete(dst_dn)

                print("  - Groups")
                dst_dns = dst.rfind("ou=Groups,o={},dc=ordered,dc={}".format(o_rdns['o'][0], service),
                                    '(objectClass=sczGroup)')
                for dst_dn, dst_entry in dst_dns.items():
                    # print("  - dstdn: {}".format(dst_dn))
                    # print("    entry: {}".format(dst_entry))

                    if dst_entry.get('description', None):
                        src_cn = dst_entry['description'][0]
                        src_dns = src.rfind("ou=Groups,o={}".format(co_name), '(cn={})'.format(src_cn))
                        if len(src_dns):
                            for src_dn, src_entry in src_dns.items():
                                pass
                                # print("   - srcdn: {}".format(src_dn))
                        else:
                            print("    - dstdn: {}".format(dst_dn))
                            print("      srcdn not found, deleting {}".format(dst_dn))
                            dst.delete(dst_dn)

                print("  - CO")
                print(f"    - dstdn: {o_dn}")
                src_dns = src.rfind('', '(o={})'.format(co_name))
                if len(src_dns) == 0:
                    print(f"   - {o_dn} not found in our services, deleting")
                    dst.rdelete(o_dn)

                print()

if __name__ == "__main__":
    create()
    cleanup()