# -*- coding: future_fstrings -*-

import util
import json
import requests

class SBS(object):
  host = None
  user = None
  password = None

  def __init__(self, config):
    self.host = config.get('host', 'localhost')
    self.user = config.get('user', 'sysread')
    self.password = config.get('passwd', 'changethispassword')

  def __get_json(self, string, title=None):
    data = json.loads(string)
    return data

  def __put_json(self, data, title=None):
    return json.dumps(data)

  def api(self, request, method='GET', headers=None, data=None):
    r = requests.request(method, url=f"{self.host}/{request}", headers=headers, auth=requests.auth.HTTPBasicAuth(self.user, self.password), data=data)
    #print('\n'.join(f'{k}: {v}' for k, v in r.headers.items()))

    if r.status_code == 200:
      try:
        return self.__get_json(r.text)
      except:
        utils.log_info(r.text)
        return r.text
    else:
      print(f"API: {request} returns: {r.status_code}")

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

    panic(f"Organisation {id} not found !")

  def collaborations(self):
    return self.api('api/collaborations/all')

  def collaboration(self, c_id):
    return self.api(f"api/collaborations/{c_id}")

  def authgroup(self, c_id, a_id):
    return self.api(f"api/authorisation_groups/{a_id}/{c_id}")

  def service_attributes(self, entity_id, uid):
    t = {
      'urn:mace:dir:attribute-def:cn': 'name',
      'urn:mace:dir:attribute-def:displayName': 'nick_name',
      'urn:mace:dir:attribute-def:eduPersonAffiliation': 'affiliation',
      'urn:mace:dir:attribute-def:givenName': 'given_name',
      'urn:mace:dir:attribute-def:isMemberOf': 'roles',
      'urn:mace:dir:attribute-def:mail': 'email',
      'urn:mace:dir:attribute-def:shortName': 'username',
      'urn:mace:dir:attribute-def:sn': 'family_name',
      'urn:mace:dir:attribute-def:uid': 'uid',
      'urn:mace:terena.org:attribute-def:schacHomeOrganization': 'schac_home_organisation',
      'urn:oid:1.3.6.1.4.1.24552.1.1.1.13': 'ssh_key',
    }
    a = self.api(f"api/user_service_profiles/attributes?service_entity_id={entity_id}&uid={uid}")
    r = {}
    for k,v in a.items():
      r[t.get(k,'other')] = v
    return r

  def service_collaborations(self):
    services = {}
    cs = self.collaborations()
    #print(f"cs: {cs}")
    for c in cs:
      c_id = c['id']
      detail = self.collaboration(c_id)
      #print(f"detail: {detail}")
      for s in detail['services']:
        #print(f"s: {s}")
        entity_id = s['entity_id']
        services.setdefault(entity_id, {})[c_id] = detail

    return services

  def users(self, c_id):
    users = {}
    co = self.collaboration(c_id)
    for u in co['collaboration_memberships']:
      users[u['user_id']] = {
        'user': u['user'],
        'roles': { 0: f"co_{co['name']}" }
      }
    for a in co['authorisation_groups']:
      a_id = a['id']
      auth_group = self.authgroup(c_id, a_id)
      for m in auth_group['collaboration_memberships']:
        users[u['user_id']]['roles'][a_id] = f"group_{a['name']}"
    return users

