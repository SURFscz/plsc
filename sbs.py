import json
import logging
from typing import Dict, List

import requests
import requests.auth
from requests.adapters import HTTPAdapter, Retry

import urllib3

import os
import socket

logger = logging.getLogger()


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
        self.timeout = config.get('timeout', None)
        self.recording_requested = config.get('recorder', False)

        if config.get("ipv4_only", False):
            import urllib3.util.connection as urllib3_connection

            urllib3_connection.allowed_gai_family = ipv4_only

        if not self.verify_ssl:
            urllib3.disable_warnings()

        self.session = requests.Session()
        retries = Retry(
            total=config.get('retry', 1),
            backoff_factor=0.5,
            status_forcelist=[503, 504]
        )

        self.session.mount(f"{self.host}", HTTPAdapter(max_retries=retries))

    @staticmethod
    def __get_json(string):
        data = json.loads(string)
        return data

    @staticmethod
    def __put_json(data):
        return json.dumps(data)

    def api(self, request, method='GET', headers=None, data=None):
        logger.debug(f"API: {request}...")

        r = self.session.request(
            method,
            url=f"{self.host}/{request}",
            headers=headers,
            auth=requests.auth.HTTPBasicAuth(self.user, self.password),
            verify=self.verify_ssl,
            timeout=self.timeout,
            data=data
        )
        #print('\n'.join(f'{k}: {v}' for k, v in r.headers.items()))

        if r.status_code == 200:
            if self.recording_requested:
                os.makedirs('/'.join(request.split('/')[:-1]), exist_ok=True)

                with open(f"./{request}", 'w') as f:
                    f.write(json.dumps(json.loads(r.text), indent=4, sort_keys=True))

            return self.__get_json(r.text)
        else:
            #logger.error(f"API: {request} returns: {r.status_code}")
            raise SBSException(f"API: {request} returns: {r.status_code}")

    def health(self):
        return self.api('health')

    def me(self):
        return self.api('api/users/me')

    def organisations(self):
        return self.api('api/organisations/all') or []

    def organisation(self, org_id):
        return self.api(f"api/organisations/{org_id}")

    def services(self):
        return self.api("api/services/all") or []

    def service(self, s_id):
        return self.api(f"api/services/{s_id}")

    def collaborations(self):
        return self.api('api/collaborations/all') or []

    def all_users(self):
        data = self.api("api/plsc/sync") or []
        return data.get('users', [])

    def collaboration(self, c_id):
        return self.api(f"api/collaborations/{c_id}")

    def group(self, c_id, g_id):
        return self.api(f"api/groups/{g_id}/{c_id}")

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

    def service_ipranges(self) -> List[str]:
        data = self.api("api/plsc/ip_ranges") or []
        return data.get('service_ipranges', [])

    def old_service_collaborations(self):
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

    def service_collaborations(self):

        result = {}
        data = self.api("api/plsc/sync")

        services = {}
        for s in data.get('services', []):
            services[s['id']] = s

        users = {}
        for u in data.get('users', []):
            users[u['id']] = u

        for o in data.get('organisations', []):

            for c in o.get('collaborations', []):
                if not c.get('global_urn', None):
                    c['global_urn'] = "{}:{}".format(o['short_name'], c['short_name'])

                c['admins'] = []
                for m in c.get('collaboration_memberships', []):
                    status = c.get('status', 'active')
                    if status == 'active':
                        status = m['status']

                    m['user'] = {**users[m['user_id']], **{'status': status}}
                    if m['role'] == 'admin':
                        c['admins'].append(m['user'])

                for g in c.get('groups', []):
                    for m in g.get('collaboration_memberships', []):
                        m['user'] = users[m['user_id']]

                c.setdefault('organisation', {})['short_name'] = o['short_name']

                for s in (o.get('services', []) + c.get('services', [])):
                    result.setdefault(
                        services[s]['entity_id'], {
                            'service_id': s,
                            'cos': {},
                            'ldap_password': services[s]['ldap_password'],
                            'aup': services[s].get('accepted_user_policy', None),
                            'pp': services[s].get('privacy_policy', None)
                        }
                    )['cos'][c['id']] = c

                c['sbs_url'] = "{}/collaborations/{}".format(self.host, c['identifier'])

        return result

    @staticmethod
    def users(co):
        users = {}
        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")
        for u in co['collaboration_memberships']:
            users[u['user_id']] = {
                'user': u['user'],
                'groups': []
            }
        for group in co['groups']:
            #g = self.group(c_id, g_id)
            for m in group['collaboration_memberships']:
                users[m['user_id']]['groups'].append(group)

        return users

    @staticmethod
    def groups(co):
        groups = {}
        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")
        for group in co['groups']:
            g_id = group['id']
            groups[g_id] = group

        logger.debug(f"GROUPS {co['short_name']} : {groups}")
        return groups

    def collaboration_users(self, c_id):
        # Warning, this function returns a dict of all CO groups
        # and one for their membership per user
        # group[0] is always the virtual CO group co_{name}
        # All other groups are called group_{name}
        co = self.collaboration(c_id)
        users: Dict[str, Dict] = {
            'groups': {
                0: f"co_{co['name']}",
            },
            'users': {}
        }
        for u in co['collaboration_memberships']:
            users['users'][u['user_id']] = {
                'user': u['user'],
                'groups': [0]
            }
        for group in co['groups']:
            g_id = group['id']
            users['groups'][g_id] = f"group_{group['name']}"
            for m in group['collaboration_memberships']:
                users['users'][m['user_id']]['groups'].append(g_id)

        logger.debug(f"USERS {c_id} : {users}")
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

        logger.debug(f"COLLABORATION GROUPS {c_id} : {groups}")
        return groups
