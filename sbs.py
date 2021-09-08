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
        logging.debug(f"API: {request}...")

        r = requests.request(method, url=f"{self.host}/{request}",
                             headers=headers,
                             auth=requests.auth.HTTPBasicAuth(self.user, self.password),
                             verify=self.verify_ssl,
                             data=data)

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

    # This method is used during Test verification, not during the PLSC cycle !
    def collaborations(self):
        return self.api('api/collaborations/all') or []

    # This method is used during Test verification, not during the PLSC cycle !
    def collaboration(self, c_id):
        return self.api(f"api/collaborations/{c_id}")

    # This method is used during PLSC cycle, it holds the total data required.
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

                for m in c.get('collaboration_memberships', []):
                    m['user'] = {**users[m['user_id']], **{'status': m['status']}}

                for g in c.get('groups', []):
                    for m in g.get('collaboration_memberships', []):
                        m['user'] = users[m['user_id']]

                c.setdefault('organisation', {})['short_name'] = o['short_name']

                for s in (o.get('services', []) + c.get('services', [])):
                    result.setdefault(services[s]['entity_id'], {})[c['id']] = c

        logging.debug("SERVICE_COLLABORATIONS: {}".format(json.dumps(result, indent=4)))
        return result

    def users(self, co):
        users = {}

        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")

        for u in co['collaboration_memberships']:
            users[u['user_id']] = {
                'user': u['user'],
                'groups': []
            }
        for group in co['groups']:
            for m in group['collaboration_memberships']:
                users[m['user_id']]['groups'].append(group)

        logging.debug("USERS: {}".format(json.dumps(users, indent=4)))
        return users

    def groups(self, co):
        groups = {}

        if not co.get('short_name'):
            raise SBSException(f"Encountered CO {co['id']} ({co['name']}) without short_name")

        for group in co['groups']:
            g_id = group['id']
            groups[g_id] = group

        logging.debug("GROUPS: {}".format(json.dumps(groups, indent=4)))
        return groups
