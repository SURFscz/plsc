# -*- coding: future_fstrings -*-
import ldap
import json
import util
import copy
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe

class mqttClient():
    enabled = False
    client_id = None
    host = None

    def __init__(self, config, *args, **kwargs):
        self.enabled = config['enabled']
        self.host = config['host']
        self.client_id = config['client_id']

    def publish(self, *args, **kwargs):
        r = False
        if self.enabled:
            try:
                publish.single(*args, hostname=self.host, retain=False, qos=1, client_id=self.client_id, **kwargs)
                print("{} {}".format(args[0], kwargs['payload']))
                r = True
            except Exception as e:
                print(f"Fail {e}")
        return r

    def subscribe(self, *args, **kwargs):
        r = False
        if self.enabled:
            try:
                msg = subscribe.simple(*args, hostname=self.host, qos=1,  client_id=self.client_id, clean_session=False, **kwargs)
                r = msg
            except Exception as e:
                print(f"Fail {e}")
        return r

def create_service(src, dst, config, sid):
    s = src.service(sid)
    service = s['entity_id']
    description = s['description']
    print(f"Creating service {sid} {service}")

    # Create service if necessary
    service_dn = f"dc={service},{dst.basedn}"
    service_entry = {'objectClass':['dcObject', 'organization'],'dc':[service],'o':[service], 'description':[description]}
    dst.store(service_dn, service_entry)
    admin_dn = 'cn=admin,' + service_dn
    admin_entry = {'objectClass':['organizationalRole', 'simpleSecurityObject'],'cn':['admin'],'userPassword':[config['pwd']]}
    dst.store(admin_dn, admin_entry)
    seq_dn = 'ou=Sequence,' + service_dn
    seq_entry = {'objectClass':['top','organizationalUnit'],'ou':['Sequence']}
    dst.store(seq_dn,seq_entry)
    uid_dn = 'cn=uidNumberSequence,ou=Sequence,' + service_dn
    uid_entry = {'objectClass':['top','device'], 'cn':['uidNumberSequence'],'serialNumber':[config['uid']]}
    dst.store(uid_dn, uid_entry)
    gid_dn = 'cn=gidNumberSequence,ou=Sequence,' + service_dn
    gid_entry = {'objectClass':['top','device'], 'cn':['gidNumberSequence'],'serialNumber':[config['gid']]}
    dst.store(gid_dn, gid_entry)

    # Ordered dn
    ordered_dn = f"dc=ordered,dc={service},{dst.basedn}"
    ordered_entry = {'objectClass':['dcObject', 'organization'],'dc':['ordered'],'o':[service]}
    dst.store(ordered_dn, ordered_entry)

def update_service(src, dst, config, sid):
    s = src.service(sid)
    service = s['entity_id']
    print(f"Updating service {sid} {service}")

    # A service update is just a create but if the
    # dn changed, we need to remove any lingering service
    # branch(es)
    create_service(src, dst, config, sid)
    
    print(f"Removing stale service branches")
    services = src.service_collaborations()
    s_dns = []
    for s in services:
        s_dns.append(f"dc={s},{dst.basedn}")

    service_dns = dst.find(f"{dst.basedn}", f"(&(objectClass=organization)", scope=sldap.SCOPE_ONLEVEL)
    for service_dn in service_dns:
        print(f"Checking {service_dn}")
        if not service_dn in s_dns:
            print(f"-  deleting")
            dst.rdelete(service_dn)

def delete_service(src, dst, config, msg):
    sid = msg['id']
    service = msg['entity_id']
    print(f"Deleting service {sid} {service}")
    service_dn = f"dc={service},{dst.basedn}"
    dst.rdelete(service_dn)


def create_collaboration(src, dst, config, cid):
    # We create the collaboration when we see a
    # collaboration_service trigger
    
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    short_name = co['short_name']

    for s in co['services']:
        service = s['entity_id']
        sid = s['id']

        # The service should exist, but we may need to create it
        # if we missed the service create earlier?
        create_service(src, dst, config, sid)

        co_dn = f"o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        co_entry = {'objectClass':['top','organization','extensibleObject'],'o':[co_identifier, cid],'description':[short_name]}
        co_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=organization)(o={co_identifier}))")
        dst.store(co_dn, co_entry)

        for ou in ['Groups', 'People']:
            ou_dn = 'ou=' + ou + ',' + co_dn
            ou_entry = {'objectClass':['top','organizationalUnit'],'ou':[ou]}
            dst.store(ou_dn, ou_entry)

        # And then there were users
        users = src.users(cid)
        #print("users: {}".format(json.dumps(users)))
        for uid, user in users.items():
            create_user(src, dst, config, cid, uid)

def update_collaboration(src, dst, config, cid):
    # TODO This does not handle CO renaming correctly!!!
    print(f"updating collaboration {cid}")
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    short_name = co['short_name']

    for s in co['services']:
        service = s['entity_id']
        # The service should exist, but we may need to create it
        # if we missed the service create earlier?
                # Create CO if necessary
        co_dn = f"o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        co_entry = {'objectClass':['top','organization','extensibleObject'],'o':[co_identifier, cid],'description':[short_name]}
        #co_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(objectClass=organization)(o={co_identifier}))")
        print(f"storing {co_dn}")
        dst.store(co_dn, co_entry)

    # If the dn changed, we need to do some cleanup
    # because group and member dns also changed
    clean_collaboration(src, dst, config, cid)

def remove_collaboration(src, dst, config, cid, sid):
    print(f"removing co {cid} from service {sid}")
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    s = src.service(sid)
    service = s['entity_id']
    service_dn = f"dc={service},{dst.basedn}"
    co_dn = f"o={co_identifier},dc=ordered,{service_dn}"
    dst.rdelete(co_dn)

def clean_collaboration(src, dst, config, cid):
    # This is untested code
    print(f"Collaboration cleanup for co {cid}")

    co = src.collaboration(cid)
    co_identifier = co['identifier']

    # Get expected groups and users
    groups = src.collaboration_groups(cid)

    services = src.service_collaborations()
    for service, cos in services.items():
        if not cid in cos:
            continue

        old_groups = {}

        # Find all groups in LDAP
        grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}", f"(&(objectClass=sczGroup))")
        for grp_dn, grp in grp_dns.items():
            name = grp['cn'][0]
            old_groups[name] = grp_dn

        # Handle co membership
        grp_id = 0
        grp_name = f"co_{co['name']}"
        print(f"CO group group {grp_name}")

        members = []
        for user_id in groups['groups'][0]['members']:
            user = groups['users'][user_id]
            uid = util.uid(user)
            user_dn = f"uid={uid},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
            members.append(user_dn)

        grp_entry = {}
        grp_entry['objectClass'] = ['extensibleObject', 'posixGroup', 'sczGroup']

        grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}", f"(&(objectClass=sczGroup)(cn={grp_name}))")
        print(f"grp_dn {grp_dn}")
        if len(grp_dns) == 1:
            old_dn, old_entry = list(grp_dns.items())[0]
            grp_entry = copy.deepcopy(old_entry)
        elif len(grp_dns) == 0:
            gid = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
            grp_entry['gidNumber'] = [gid]
            grp_entry['sczMember'] = [ user_dn ]
        else:
            print("Too many dn's, this shouldn't happen")

        # Here's the magic: Build the new group entry
        grp_entry['sczMember'] = members
        grp_entry['cn'] = [ grp_name ]
        grp_entry['description'] = [ grp_id ]

        ldif = dst.store(grp_dn, grp_entry)
        print(f"update group: {grp_dn}")

        grps = []
        for gid, grp in groups['groups'].items():
            grps.append(grp['name'])
        for name, grp_dn in old_groups.items():
            if not name in grps:
                print(f"remove group: {grp_dn}")
                dst.rdelete(grp_dn)

def delete_collaboration(src, dst, config, cid):
    service_dns = dst.find(dst.basedn, f"(&(objectClass=dcObject)(ObjectClass=organization))", scope=ldap.SCOPE_ONELEVEL)
    for service_dn in service_dns:
        co_dns = dst.find(service_dn, f"(&(objectClass=organization)(o={cid}))")
        for co_dn in co_dns:
            print(f"deleting co {co_dn}")
            dst.rdelete(co_dn)

def collab_member(src, dst, config, cid, uid):
    # This is untested code
    # Create groups is not user specific, which is a waste
    # Do we need to create the user first in case we missed
    # user create?
    # create_user(src, dst, config, cid, uid):
    users = src.users(cid)
    create_user_groups(src, dst, config, cid, users[uid])

def create_user(src, dst, config, cid, uid):
    users = src.users(cid)
    user = users[uid]
    uid = util.uid(user['user'])
    co = src.collaboration(cid)
    co_identifier = co['identifier']

    services = src.service_collaborations()
    for service, cos in services.items():
        if not cid in cos:
            continue
        service_attributes = src.service_attributes(service, user['user']['uid'])

        dst_entry = {}
        dst_entry['objectClass'] = ['inetOrgPerson', 'person', 'posixAccount', 'ldapPublicKey', 'eduPerson']
        dst_dn = f"uid={uid},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"

        dst_dns = dst.rfind(f"dc=ordered,dc={service}", f"(&(ObjectClass=person)(uid={uid}))")
        if len(dst_dns) >= 1:
            old_dn, old_entry = list(dst_dns.items())[0]
            dst_entry['uidNumber'] = old_entry.get('uidNumber', 0)
            dst_entry['gidNumber'] = old_entry.get('gidNumber', 0)
        elif len(dst_dns) == 0:
            uidnumber = dst.get_sequence(f"cn=uidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
            dst_entry['uidNumber'] = [uidnumber]
            gidnumber = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
            dst_entry['gidNumber'] = [gidnumber]

        # Here's the magic: Build the new person entry
        dst_entry['uid'] = [uid]
        dst_entry['cn'] = service_attributes.get('name', ['n/a'])
        dst_entry['sn'] = service_attributes.get('family_name', ['n/a'])
        dst_entry['mail'] = service_attributes.get('email', [])
        dst_entry['homeDirectory'] = ['/home/{}'.format(uid.encode('unicode-escape').decode('ascii'))]
        dst_entry['sshPublicKey'] = service_attributes.get('ssh_key', None) or ['n/a']
        eppn = f"{user['user']['id']}@{co['short_name']}.scz.net"
        dst_entry['eduPersonScopedAffiliation'] = [eppn]

        ldif = dst.store(dst_dn, dst_entry)
        print(f"create user: {dst_dn}")

        #roles = user['roles']
        create_user_groups(src, dst, config, cid, user)

def create_user_groups(src, dst, config, cid, user):
    print(f"Creating groups for cid {cid} uid {user['user']['id']}")
    services = src.service_collaborations()

    for service, s in services.items():
        if not cid in s:
            continue

        print(f"Creating roles")
        groups = user['roles']
        uid = util.uid(user['user'])
        co = src.collaboration(cid)
        co_identifier = co['identifier']
        user_dn = f"uid={uid},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        for grp_id, grp_name in groups.items():
            print(f"grp_id {grp_id} grp_name {grp_name}")
            grp_entry = {}
            grp_entry['objectClass'] = ['extensibleObject', 'posixGroup', 'sczGroup']

            grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"

            grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}", f"(&(objectClass=sczGroup)(cn={grp_name}))")
            if len(grp_dns) == 1:
                old_dn, old_entry = list(grp_dns.items())[0]
                grp_entry = copy.deepcopy(old_entry)
                sczMembers =  old_entry.get('sczMember', [])
                if user_dn not in sczMembers:
                    grp_entry.setdefault('sczMember', []).append(user_dn)
            elif len(grp_dns) == 0:
                gid = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
                grp_entry['gidNumber'] = [gid]
                grp_entry['sczMember'] = [ user_dn ]
            else:
                print("Too many dn's, this shouldn't happen")

            # Here's the magic: Build the new group entry
            grp_entry['cn'] = [grp_name]
            grp_entry['description'] = [grp_id]

            ldif = dst.store(grp_dn, grp_entry)
            print(f"create group: {grp_dn}")

def create_group(src, dst, config, cid, gid):
    print(f"Creating group")
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    group = src.group(cid, gid)
    grp_id = gid
    grp_name = f"group_{group['name']}"

    print(f"grp_id {grp_id} grp_name {grp_name}")
    grp_entry = {}
    grp_entry['objectClass'] = ['extensibleObject', 'posixGroup', 'sczGroup']

    services = src.service_collaborations()
    for service, cos in services.items():
        if not cid in cos:
            continue

        grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        gid_number = dst.get_sequence(f"cn=gidNumberSequence,ou=Sequence,dc={service},{dst.basedn}")
        grp_entry['gidNumber'] = [gid_number]
        grp_entry['sczMember'] = []

        # Here's the magic: Build the new group entry
        grp_entry['cn'] = [grp_name]
        grp_entry['description'] = [grp_id]

        ldif = dst.store(grp_dn, grp_entry)
        print(f"create group: {grp_dn}")

def remove_group_users(src, dst, config, cid, gid):
    print(f"Remove users group {gid} in co {cid}")
    services = src.service_collaborations()
    for service, s in services.items():
        if not s.get(int(cid), False):
            continue
        group = src.group(cid, gid)
        clean_group(src, dst, config, cid, service, group)

def delete_group(src, dst, config, cid, gid, msg):
    print(f"Deleting group {gid} in co {cid}")
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    grp_name = msg['name']
    grp_cn = f"group_{grp_name}"

    services = src.service_collaborations()
    for service, cos in services.items():
        if not cid in cos:
            continue
        grp_dn = f"cn={grp_cn},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
        dst.rdelete(grp_dn)

def group_users(src, dst, config, cid, gid):
    print(f"Doing memberships for group {gid} in co {cid}")
    services = src.service_collaborations()
    users = src.users(cid)
    for uid, user in users.items():
        create_user(src, dst, config, cid, uid)

def clean_group(src, dst, config, cid, service, group):
    print(f"Cleaning role for co {cid} in service {service}")
    #print(f"role {role}")
    co = src.collaboration(cid)
    co_identifier = co['identifier']
    grp_id = group['id']
    grp_name = "group_" + group['name']
    users = src.users(cid)
    print(f"grp_id {grp_id} name {grp_name}")
    members = []
    for uid, user in users.items():
        print(f"uid {uid} user {user['user']['uid']} {json.dumps(user)}")
        if grp_id in user['roles']:
            uid = util.uid(user['user'])
            user_dn = f"uid={uid},ou=People,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
            members.append(user_dn)

    grp_dn = f"cn={grp_name},ou=Groups,o={co_identifier},dc=ordered,dc={service},{dst.basedn}"
    grp_dns = dst.rfind(f"ou=Groups,o={co_identifier},dc=ordered,dc={service}", f"(&(objectClass=sczGroup)(cn={grp_name}))")
    print(f"grp_dn {grp_dn}")
    if len(grp_dns) == 1:
        old_dn, old_entry = list(grp_dns.items())[0]
        grp_entry = copy.deepcopy(old_entry)
        grp_entry['sczMember'] = members
    else:
        print("No or too many dn's, this shouldn't happen?")

    # Here's the magic: Build the new group entry
    grp_entry['cn'] = [grp_name]
    grp_entry['description'] = [grp_id]

    ldif = dst.store(grp_dn, grp_entry)
    print(f"update group: {grp_dn}")


def test(src, dst, config, cid):
    users = src.collaboration_users(cid)
    print("users: {}".format(json.dumps(users)))
    groups = src.collaboration_groups(cid)
    print("groups: {}".format(json.dumps(groups)))

