import json
import ldap

import logging

logger = logging.getLogger()


def make_secret(password):
    import passlib.hash
    crypted = passlib.hash.sha512_crypt.hash(password)
    return '{SSHA}' + crypted.decode('ascii')


def escape_dn_chars(s):
    """
    Escape dn characters to prevent injection according to RFC 4514.
    Refer: https://ldapwiki.com/wiki/Wiki.jsp?page=DN%20Escape%20Values
    """

    s = s.replace('\\', r'\5C')
    s = s.replace(r',', r'\2C')
    s = s.replace(r'#', r'\23')
    s = s.replace(r'+', r'\2B')
    s = s.replace(r'<', r'\3C')
    s = s.replace(r'>', r'\3E')
    s = s.replace(r';', r'\3B')
    s = s.replace(r'"', r'\22')
    s = s.replace(r'=', r'\3D')
    s = s.replace('\x00', r'\00')

    return s


def dn2rdns(dn):
    rdns = {}
    r = ldap.dn.str2dn(dn)
    for rdn in r:
        a, v, t = rdn[0]
        rdns.setdefault(a, []).append(v)
    return rdns


def find_cos(c, service):
    cos = {}
    r = c.find(None, "(&(objectClass=organization)(labeledURI={}))".format(service),
               ['o', 'dnQualifier', 'description'])
    for dn, entry in r.items():
        rdns = dn2rdns(dn)
        j = entry.get('description', None)
        description = {}
        if j:
            try:
                description = json.loads(j[0])
            except Exception as e:
                print("find_cos: {}".format(e))

        if entry.get('dnQualifier', None):
            cos[rdns['o'][0]] = entry['dnQualifier']
        elif description.get('identifier', None):
            cos[rdns['o'][0]] = [description['identifier']]
        elif description.get('comanage_id', None):
            cos[rdns['o'][0]] = [description['comanage_id']]
        else:
            cos[rdns['o'][0]] = entry['o']

    return cos


def find_services(c):
    services = []
    r = c.find(None, '(&(objectClass=organization)(labeledURI=*))', ['labeledURI'])
    for dn, entry in r.items():
        services.extend(entry['labeledURI'])
    return list(set(services))


def find_ordered_services(c):
    services = []
    r = c.find(None, '(objectClass=dcObject)', ['dc'], scope=ldap.SCOPE_ONELEVEL)
    for dn, entry in r.items():
        services.extend(entry['dc'])
    return list(set(services))


def find_collaborations(c, services):
    col = {}
    for service in services:
        col[service] = []
        cos = find_cos(c, service)
        for co in cos.items():
            col[service].append(co)

    return col


def find_ordered_collaborations(c, services):
    col = {}
    for service in services:
        col[service] = []
        cos = c.rfind(f"dc=ordered,dc={service}", "(objectClass=organization)", ['o'], scope=ldap.SCOPE_ONELEVEL)
        for co, entry in cos.items():
            col[service].append(entry['o'][0])

    return col


def uid(user):
    username = user.get('uid', None)
    if not username:
        raise Exception("User: {} does not contain username")

    if isinstance(username, list):
        username = username[0]

    return ldap.dn.escape_dn_chars(username)
