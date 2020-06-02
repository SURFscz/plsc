#!/usr/bin/env python
# -*- coding: future_fstrings -*-

import sys
import yaml, re
import socket
import copy
import util

def flatten(src, dst, sbs, config, cid):
    print(f"--- Flatten {cid} ---")
    vc = {
    'users': set(), # only unique values
    'groups': set(),
    }

    collaborations = sbs.service_collaborations()

    # Create phase
    print("--- Create ---")
    for service, cos in collaborations.items():
        if not cid in cos:
            continue
        print("service: {}".format(service))
        for cid in cos:
            co = sbs.collaboration(cid)
            co_id = co['identifier']
            print(f"- co: {co_id}")

            co_dn = f"dc=flat,dc={service},{dst.basedn}"

            # Flat dn
            flat_dns = dst.rfind(f"dc={service}", "(&(objectClass=dcObject)(dc=flat))")
            if len(flat_dns) == 0:
                flat_dn = f"dc=flat,dc={service},{dst.basedn}"
                flat_entry = {'objectClass':['dcObject', 'organization'],'dc':['flat'],'o':[service]}
                dst.add(flat_dn, flat_entry)
                for ou in ['Groups', 'People']:
                    ou_dn = 'ou=' + ou + ',' + flat_dn
                    ou_entry = {'objectClass':['top','organizationalUnit'],'ou':[ou]}
                    dst.add(ou_dn, ou_entry)

            print("  - People")
            src_dns = src.rfind(f"ou=People,o={co_id},dc=ordered,dc={service}", '(ObjectClass=person)')

            for src_dn, src_entry in src_dns.items():
                print("  - srcdn: {}".format(src_dn))
                src_uid = src_entry['uid'][0]

                vc['users'].add(src_uid)

                dst_dn = f"uid={src_uid},ou=People,{co_dn}"
                dst_dns = dst.rfind("ou=People,dc=flat,dc={}".format(service), "(&(ObjectClass=person)(uid={}))".format(src_uid))
                #ipdb.set_trace()
                # We can't just store People, we need to merge attributes
                if len(dst_dns) == 1:
                    old_dn, old_entry = list(dst_dns.items())[0]
                    for k,v in old_entry.items():
                        src_entry.setdefault(k,[]).extend(v)
                        src_entry[k] = list(set(src_entry[k]))
                ldif = dst.store(dst_dn, src_entry)
                print("    - store: {}".format(ldif))

            print("  - Groups")
            grp_dns = src.rfind(f"ou=Groups,o={co_id},dc=ordered,dc={service}", '(objectClass=sczGroup)')

            for grp_dn, grp_entry in grp_dns.items():
                print("  - grpdn: {}".format(grp_dn))

                grp_rdns = util.dn2rdns(grp_dn)
                grp_cn = grp_rdns['cn'][0]
                #print(f"cn: {grp_cn}")

                vc['groups'].add(grp_cn)

                members = []
                scz_members = grp_entry.get('sczMember', [])

                # Build members, remove o= from member DN's
                for member in scz_members:
                    member_rdns = util.dn2rdns(member)
                    # members can be persons or groups
                    member_uid = member_rdns.get('uid', [])
                    member_cn = member_rdns.get('cn', [])
                    if len(member_uid):
                      member_dn = f"uid={member_uid[0]},ou=People,{co_dn}"
                    elif len(member_cn):
                      member_dn = f"cn={member_cn[0]},ou=Groups,{co_dn}"
                    else:
                      # no valid member found?
                      continue
                    members.append(member_dn)
                    #print(f"uid: {member_dn}")

                old_entry = copy.deepcopy(grp_entry)
                grp_entry['sczMember'] = members

                dst_dn = f"cn={grp_cn},ou=Groups,{co_dn}"
                dst_dns = dst.rfind(f"ou=Groups,dc=flat,dc={service}", f"(&(ObjectClass=sczGroup)(cn={grp_cn}))")

                ldif = dst.store(dst_dn, grp_entry)
                print("    - store: {}".format(ldif))

            print()

    #print(f"vc: {vc}")

    # Cleanup phase
    print("--- Cleanup ---")
    for service, cos in collaborations.items():
        print("service: {}".format(service))

        print("  - People")
        dst_dns = dst.rfind(f"ou=People,dc=flat,dc={service}", "(objectClass=person)")
        for dst_dn, dst_entry in dst_dns.items():
            #print("  - dstdn: {}".format(dst_dn))
            #print("    entry: {}".format(dst_entry))

            if dst_entry.get('uid', None):
                src_uid = dst_entry['uid'][0]
                src_dns = src.rfind(f"dc=ordered,dc={service}", f"(uid={src_uid})")
                if len(src_dns):
                    for src_dn, src_entry in src_dns.items():
                        pass
                        #print("   - srcdn: {}".format(src_dn))
                else:
                    print("    - dstdn: {}".format(dst_dn))
                    print("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)

        print("  - Groups")
        dst_dns = dst.rfind(f"ou=Groups,dc=flat,dc={service}", "(objectClass=sczGroup)")
        for dst_dn, dst_entry in dst_dns.items():
            #print("  - dstdn: {}".format(dst_dn))
            #print("    entry: {}".format(dst_entry))

            if dst_entry.get('cn', None):
                src_cn = dst_entry['cn'][0]
                src_dns = src.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=sczGroup)(cn={src_cn}))")
                if len(src_dns):
                    for src_dn, src_entry in src_dns.items():
                        pass
                        #print("   - srcdn: {}".format(src_dn))
                else:
                    print("    - dstdn: {}".format(dst_dn))
                    print("      srcdn not found, deleting {}".format(dst_dn))
                    dst.delete(dst_dn)

        print()
