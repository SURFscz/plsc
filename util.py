import json
import ldap

import logging

logger = logging.getLogger()


def make_secret(password):
    import passlib.hash
    crypted = passlib.hash.sha512_crypt.hash(password)
    return '{SSHA}' + crypted.decode('ascii')


SPECIAL_DN_CHARACTERS = "\\,+<>;\"= "
SPECIAL_FILTER_CHARACTERS = "\\*()"


def escape_special_characters(s, special_characters):
    """
    Escape dn characters to prevent injection according to RFC 4514.
    """

    for c in special_characters:
        s = s.replace(c, "\\" + hex(ord(c))[2:].upper())

    return s


def escape_dn_chars(s):
    """
    Escape dn characters to prevent injection according to RFC 4514.
    Refer: https://ldapwiki.com/wiki/Wiki.jsp?page=DN%20Escape%20Values

    PS. Explicitly do not use below method, that one is failing
    return ldap.dn.escape_dn_chars(s)
    """

    return escape_special_characters(s, SPECIAL_DN_CHARACTERS)


def escape_filter_chars(s):
    """
    Escape filter characters to prevent injection according to RFC 4514.
    Refer: https://social.technet.microsoft.com/wiki/
    contents/articles/5392.active-directory-ldap-syntax-filters.aspx#Special_Characters
    """

    return escape_special_characters(s, SPECIAL_FILTER_CHARACTERS)


def dn2rdns(dn):
    rdns = {}
    r = ldap.dn.str2dn(dn)
    for rdn in r:
        a, v, t = rdn[0]
        rdns.setdefault(a, []).append(v)
    return rdns


def find_cos(c, service):
    cos = {}

    r = c.find(
        None,
        "(&(objectClass=organization)(labeledURI={}))".format(
            escape_filter_chars(escape_dn_chars(service))
        ),
        ['o', 'dnQualifier', 'description']
    )

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
        cos = c.rfind(
            f"dc=ordered,dc={escape_dn_chars(service)}",
            "(objectClass=organization)", ['o'],
            scope=ldap.SCOPE_ONELEVEL
        )
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
