#!/usr/bin/env python3

from typing import List

import logging
import sys
import yaml
import copy
import os
import util

from sldap import SLdap

# import ipdb
# ipdb.set_trace()

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))


# Create phase
def create(src, dst):
    global vc
    overruling_status = 'active'

    services = util.find_ordered_services(src)
    logging.debug(f"s: {services}")

    collaborations = util.find_ordered_collaborations(src, services)
    logging.debug(f"c: {collaborations}")

    logging.debug("--- Create ---")
    for service, cos in collaborations.items():

        # voPersonStatus is a special case (per service)
        voPersonStatus = {}
        people_entries = {}
        group_entries = {}

        logging.debug("service: {}".format(service))

        # Create flat dn if it doesn't exist
        flat_dns = dst.rfind(f"dc={service}", "(&(objectClass=dcObject)(dc=flat))")
        if len(flat_dns) == 0:
            flat_dn = f"dc=flat,dc={service},{dst.basedn}"
            flat_entry = {'objectClass': ['dcObject', 'organizationalUnit'], 'dc': ['flat'], 'ou': ['flat']}
            dst.add(flat_dn, flat_entry)
            for ou in ['Groups', 'People']:
                ou_dn = 'ou=' + ou + ',' + flat_dn
                ou_entry = {'objectClass': ['top', 'organizationalUnit'], 'ou': [ou]}
                dst.add(ou_dn, ou_entry)

        for co_id in cos:
            logging.debug(f"- co: {co_id}")

            src_dn = src.rfind(f"o={co_id},dc=ordered,dc={service}", '(ObjectClass=organization)')
            src_co = src_dn.get(f"o={co_id},dc=ordered,dc={service},{src.basedn}", {})
            src_mail = src_co.get('mail', [])
            src_status = src_co.get('organizationalStatus', ['active'])
            logging.debug(f"src_mail: {src_mail}")

            co_dn = f"dc=flat,dc={service},{dst.basedn}"

            logging.debug("  - People")
            src_dns = src.rfind(f"ou=People,o={co_id},dc=ordered,dc={service}", '(ObjectClass=person)')

            for src_dn, src_entry in src_dns.items():
                logging.debug("  - srcdn: {}".format(src_dn))
                src_uid = src_entry['uid'][0]

                current_status = src_entry.get('voPersonStatus', [overruling_status])[0]
                voPersonStatus.setdefault(src_uid, []).append(current_status)
                src_entry['voPersonStatus'] = [overruling_status] \
                    if overruling_status in voPersonStatus[src_uid] else [current_status]

                dst_dn = f"uid={src_uid},ou=People,{co_dn}"
                people_entries[dst_dn] = src_entry

            logging.debug("  - Groups")
            grp_dns = src.rfind(f"ou=Groups,o={co_id},dc=ordered,dc={service}", '(objectClass=groupOfMembers)')

            for grp_dn, grp_entry in grp_dns.items():
                logging.debug("  - group_dn: {}".format(grp_dn))

                grp_rdns = util.dn2rdns(grp_dn)
                grp_cn = f"{co_id}.{grp_rdns['cn'][0]}"
                logging.debug(f"cn: {grp_cn}")

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
                new_entry['mail'] = src_mail
                new_entry['organizationalStatus'] = src_status

                dst_dn = f"cn={grp_cn},ou=Groups,{co_dn}"
                group_entries[dst_dn] = new_entry

        # We need to write People first so that
        # memberOf overlay can find the members
        for dst_dn, dst_entry in people_entries.items():
            ldif = dst.store(dst_dn, dst_entry)
            logging.debug(f"    - store: {dst_dn} {ldif}")

        # Then Groups
        for dst_dn, dst_entry in group_entries.items():
            ldif = dst.store(dst_dn, dst_entry)
            logging.debug(f"    - store: {dst_dn} {ldif}")


# Cleanup phase
def cleanup(src, dst):
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
                if len(src_dns) == 0:
                    logging.debug("    - dstdn: {}".format(dst_dn))
                    logging.debug("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)

        logging.debug("  - Groups")
        dst_dns = dst.rfind(f"ou=Groups,dc=flat,dc={service}", "(objectClass=groupOfMembers)")
        for dst_dn, dst_entry in dst_dns.items():
            #logging.debug("  - dstdn: {}".format(dst_dn))
            #logging.debug("    entry: {}".format(dst_entry))

            if dst_entry.get('cn', None):
                org = dst_entry['cn'][0].split('.')[-3]
                co = dst_entry['cn'][0].split('.')[-2]
                src_cn = dst_entry['cn'][0].split('.')[-1]

                # Verify that referenced CO is still operational CO in Ordered structure
                # If not, remove this object.
                logging.debug(f"CHECKING CO : {org}.{co}...")
                src_dns = src.rfind(
                    f"dc=ordered,dc={service}",
                    f"(&(objectClass=organization)(o={org}.{co}))")
                if len(src_dns) == 0:
                    logging.debug("    - dstdn: {}".format(dst_dn))
                    logging.debug("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)
                else:
                    # Verify that group still valid group within referenced CO...
                    src_dns = src.rfind(
                        f"o={org}.{co},dc=ordered,dc={service}",
                        f"(&(objectClass=groupOfMembers)(cn={src_cn}))")
                    #if len(src_dns):
                    #    for src_dn, src_entry in src_dns.items():
                    #        pass
                    #        #logging.debug("   - srcdn: {}".format(src_dn))
                    if len(src_dns) == 0:
                        logging.debug("    - dstdn: {}".format(dst_dn))
                        logging.debug("      srcdn not found, deleting {}".format(dst_dn))
                        dst.delete(dst_dn)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = SLdap(config['ldap']['dst'])
    dst = SLdap(config['ldap']['dst'])

    create(src, dst)
    cleanup(src, dst)
