import json
import logging
import requests
import requests.auth
import urllib3

import os
import socket

def ipv4_only():
    return socket.AF_INET

class SBSException(Exception):
    pass


class SBS(object):
    host = None
    user = None
    password = None

    def __init__(self, config):
        self.host = config.get('host', 'localhost')
        self.user = config.get('user', 'sysread')
        self.password = config.get('passwd', 'changethispassword')
        self.verify_ssl = config.get('verify_ssl', True)
        self.recording_requested = config.get('recorder', False)

        if config.get("ipv4_only", False):
            import urllib3.util.connection as urllib3_connection

            urllib3_connection.allowed_gai_family = ipv4_only

        if not self.verify_ssl:
            urllib3.disable_warnings()

    @staticmethod
    def __get_json(string):
        data = json.loads(string)
        return data

    @staticmethod
    def __put_json(data):
        return json.dumps(data)

    def api(self, request, method='GET', headers=None, data=None):
        logging.info(f"API: {request}...")

        r = requests.request(method, url=f"{self.host}/{request}",
                             headers=headers,
                             auth=requests.auth.HTTPBasicAuth(self.user, self.password),
                             verify=self.verify_ssl,
                             data=data)
        #print('\n'.join(f'{k}: {v}' for k, v in r.headers.items()))

        if r.status_code == 200:
            if self.recording_requested:
                os.makedirs('/'.join(request.split('/')[:-1]), exist_ok = True)

                with open(f"./{request}", 'w') as f:
                    f.write(json.dumps(json.loads(r.text), indent=4, sort_keys=True))

            return self.__get_json(r.text)
        else:
            logging.error(f"API: {request} returns: {r.status_code}")

        return None

    def health(self):
        return self.api('health')

    def me(self):
        return self.api('api/users/me')

    def organisations(self):
        return self.api('api/organisations/all')

    def organisation(self, org_id):
        organisations = self.organisations()
        for o in organisations:
            if o['id'] == org_id:
                return o

        raise Exception(f"Organisation {id} not found !")

    def service(self, s_id):
        return self.api(f"api/services/{s_id}")

    def collaborations(self):
        return self.api('api/collaborations/all')

    def collaboration(self, c_id):
        return self.api(f"api/collaborations/{c_id}")

    def service_attributes(self, uid):
        # t = {
        #     'urn:mace:dir:attribute-def:cn': 'name',
        #     'urn:mace:dir:attribute-def:displayName': 'nick_name',
        #     'urn:mace:dir:attribute-def:eduPersonAffiliation': 'affiliation',
        #     'urn:mace:dir:attribute-def:givenName': 'given_name',
        #     'urn:mace:dir:attribute-def:isMemberOf': 'roles',
        #     'urn:mace:dir:attribute-def:mail': 'email',
        #     'urn:mace:dir:attribute-def:shortName': 'username',
        #     'urn:mace:dir:attribute-def:sn': 'family_name',
        #     'urn:mace:dir:attribute-def:uid': 'uid',
        #     'urn:mace:terena.org:attribute-def:schacHomeOrganization': 'schac_home_organisation',
        #     'urn:oid:1.3.6.1.4.1.24552.1.1.1.13': 'ssh_key',
        # }
        # a = self.api(f"api/users/attributes?service_entity_id={entity_id}&uid={uid}")
        # r = {}
        # for k,v in a.items():
        #     r[t.get(k,'other')] = v
        # return r
        a = self.api(f"api/users/user?uid={uid}")
        return a

    def service_collaborations(self):
        services = {}
        cs = self.collaborations()
        #print(f"cs: {cs}")
        for c in cs:
            c_id = c['id']
            detail = self.collaboration(c_id)
            # temporary hack because global_urn is not always defined yet
            if not detail.get('global_urn'):
                detail['global_urn'] = "{}:{}".format(detail['organisation']['short_name'], detail['short_name'])
            #print(f"detail: {detail}")
            for s in detail['services'] + detail['organisation']['services']:
                #print(f"s: {s}")
                entity_id = s['entity_id']
                services.setdefault(entity_id, {})[c_id] = detail

        return services

    def users(self, co):
        users = {}
        groups = self.groups(co)
        #co = self.collaboration(c_id)
        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")
        for u in co['collaboration_memberships']:
            users[u['user_id']] = {
                'user': u['user'],
                'groups': []
            }
        for group in co['groups']:
            for m in group['collaboration_memberships']:
            #g = self.group(c_id, g_id)
            for m in group['collaboration_memberships']:
                users[m['user_id']]['groups'].append(group)

        return users

    def groups(self, co):
        groups = {}
        #co = self.collaboration(c_id)
        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {c_id} ({co['name']}) without short_name")
        for group in co['groups']:
            g_id = group['id']
            #g = self.group(c_id, g_id)
            groups[g_id] = group
        return groups

    def groups(self, co):
        groups = {}
        #co = self.collaboration(c_id)
        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")
        for group in co['groups']:
            g_id = group['id']
            groups[g_id] = group

        logging.debug(f"GROUPS {co['id]']} : {groups}")
        return groups

    def collaboration_users(self, c_id):
        # Warning, this function returns a dict of all CO groups
        # and one for their membership per user
        # group[0] is always the virtual CO group co_{name}
        # All other groups are called group_{name}
        co = self.collaboration(c_id)
        users = {
            'groups': {
                0: f"co_{co['name']}",
            },
            'users': {}
        }
        for u in co['collaboration_memberships']:
            users['users'][u['user_id']] = {
                'user': u['user'],
                'groups': [ 0 ]
            }
        for group in co['groups']:
            g_id = group['id']
            users['groups'][g_id] = f"group_{group['name']}"
            for m in g['collaboration_memberships']:
                users['users'][m['user_id']]['groups'].append(g_id)

        logging.debug(f"USERS {c_id} : {users}")
        return users

    def collaboration_groups(self, c_id):
        # Warning, this function returns a dict for all CO users
        # and one their membership per group
        # group[0] is always the virtual CO group co_{name}
        # All other groups are called group_{name}
        co = self.collaboration(c_id)
        groups = {
            'users': {},
            'groups': {
                0: {
                    'members': []
                },
            },
        }
        for u in co['collaboration_memberships']:
            groups['groups'][0]['name'] = f"co_{co['name']}"
            groups['groups'][0]['members'].append(u['user_id'])
            groups['users'][u['user_id']] = u['user']
        for group in co['groups']:
            g_id = group['id']
            groups['groups'][g_id] = {
                'members': []
            }
            g = self.group(c_id, g_id)
            for m in g['collaboration_memberships']:
                groups['groups'][g_id]['members'].append(m['user_id'])
                groups['groups'][g_id]['name'] = f"group_{g['name']}"
                groups['users'][m['user_id']] = m['user']

        logging.debug(f"COLLABORATION GROUPS {c_id} : {groups}")
        return groups

