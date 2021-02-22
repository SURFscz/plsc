#!/usr/bin/env python3

from typing import List

import logging

import sys
import yaml
import copy

import util
from sldap import sLDAP

#import ipdb
#ipdb.set_trace()

vc = {
    'users': set(),  # only unique values
    'groups': set(),
}

# Create phase
def create(src, dst):
    global vc

    services = util.find_ordered_services(src)
    logging.debug(f"s: {services}")

    collaborations = util.find_ordered_collaborations(src, services)
    logging.debug(f"c: {collaborations}")

    logging.debug("--- Create ---")
    for service, cos in collaborations.items():
        logging.debug("service: {}".format(service))
        for co_id in cos:
            logging.debug(f"- co: {co_id}")

            co_dn = f"dc=flat,dc={service},{dst.basedn}"

            # create Flat dn it is doesn't exist
            flat_dns = dst.rfind(f"dc={service}", "(&(objectClass=dcObject)(dc=flat))")
            if len(flat_dns) == 0:
                flat_dn = f"dc=flat,dc={service},{dst.basedn}"
                flat_entry = {'objectClass': ['dcObject', 'organizationalUnit'], 'dc': ['flat'], 'ou': ['flat']}
                dst.add(flat_dn, flat_entry)
                for ou in ['Groups', 'People']:
                    ou_dn = 'ou=' + ou + ',' + flat_dn
                    ou_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': [ou]}
                    dst.add(ou_dn, ou_entry)

            logging.debug("  - People")
            src_dns = src.rfind(f"ou=People,o={co_id},dc=ordered,dc={service}", '(ObjectClass=person)')

            for src_dn, src_entry in src_dns.items():
                logging.debug("  - srcdn: {}".format(src_dn))
                src_uid = src_entry['uid'][0]

                vc['users'].add(src_uid)

                dst_dn = f"uid={src_uid},ou=People,{co_dn}"
                dst_dns = dst.rfind("ou=People,dc=flat,dc={}".format(service),
                                    "(&(ObjectClass=person)(cn={}))".format(src_uid))

                # We can't just store People, we need to merge attributes
                if len(dst_dns) == 1:
                    old_dn, old_entry = list(dst_dns.items())[0]
                    for k, v in old_entry.items():
                        src_entry.setdefault(k, []).extend(v)
                        src_entry[k] = list(set(src_entry[k]))
                ldif = dst.store(dst_dn, src_entry)
                logging.debug("    - store: {}".format(ldif))

            logging.debug("  - Groups")
            grp_dns = src.rfind(f"ou=Groups,o={co_id},dc=ordered,dc={service}", '(objectClass=groupOfMembers)')

            for grp_dn, grp_entry in grp_dns.items():
                logging.debug("  - group_dn: {}".format(grp_dn))

                grp_rdns = util.dn2rdns(grp_dn)
                grp_cn = f"{co_id}.{grp_rdns['cn'][0]}"
                logging.debug(f"cn: {grp_cn}")

                vc['groups'].add(grp_cn)

                members: List[str] = []
                scz_members = grp_entry.get('member', [])

                # Build members, remove o= from member DN's
                for member in scz_members:
                    member_rdns = util.dn2rdns(member)
                    # members can be persons or groups
                    member_uid = member_rdns.get('uid', [])
                    member_cn = member_rdns.get('cn', [])
                    if len(member_uid):
                        member_dn = f"uid={member_uid[0]},ou=People,{co_dn}"
                    elif len(member_cn):
                        member_dn = f"cn={member_cn[0]},ou=People,{co_dn}"
                    else:
                        # no valid member found?
                        continue
                    members.append(member_dn)
                    #logging.debug(f"uid: {member_dn}")

                new_entry = copy.deepcopy(grp_entry)
                new_entry['cn'] = [grp_cn]
                new_entry['member'] = members

                dst_dn = f"cn={grp_cn},ou=Groups,{co_dn}"
                dst_dns = dst.rfind(f"ou=Groups,dc=flat,dc={service}", f"(&(ObjectClass=groupOfMembers)(cn={grp_cn}))")

                ldif = dst.store(dst_dn, new_entry)
                logging.debug("    - store: {}".format(ldif))


# Cleanup phase
def cleanup(src, dst):
    global vc
    
    services = util.find_ordered_services(src)
    collaborations = util.find_ordered_collaborations(src, services)

    logging.debug("--- Cleanup ---")
    for service, _ in collaborations.items():
        logging.debug("service: {}".format(service))

        logging.debug("  - People")
        dst_dns = dst.rfind(f"ou=People,dc=flat,dc={service}", "(objectClass=person)")
        for dst_dn, dst_entry in dst_dns.items():
            #logging.debug("  - dstdn: {}".format(dst_dn))
            #logging.debug("    entry: {}".format(dst_entry))

            if dst_entry.get('uid', None):
                src_uid = dst_entry['uid'][0]
                src_dns = src.rfind(f"dc=ordered,dc={service}", f"(uid={src_uid})")
                if len(src_dns):
                    for src_dn, src_entry in src_dns.items():
                        pass
                        #logging.debug("   - srcdn: {}".format(src_dn))
                else:
                    logging.debug("    - dstdn: {}".format(dst_dn))
                    logging.debug("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)

        logging.debug("  - Groups")
        dst_dns = dst.rfind(f"ou=Groups,dc=flat,dc={service}", "(objectClass=groupOfMembers)")
        for dst_dn, dst_entry in dst_dns.items():
            #logging.debug("  - dstdn: {}".format(dst_dn))
            #logging.debug("    entry: {}".format(dst_entry))

            if dst_entry.get('cn', None):
                src_cn = dst_entry['cn'][0].split('.')[-1]
                src_dns = src.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=groupOfMembers)(cn={src_cn}))")
                if len(src_dns):
                    for src_dn, src_entry in src_dns.items():
                        pass
                        #logging.debug("   - srcdn: {}".format(src_dn))
                else:
                    logging.debug("    - dstdn: {}".format(dst_dn))
                    logging.debug("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = sLDAP(config['ldap']['dst'])
    dst = sLDAP(config['ldap']['dst'])

    create(src, dst)
    cleanup(src)
