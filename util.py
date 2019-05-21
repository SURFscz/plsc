import os, hashlib, json
import ldap
from base64 import b64encode

def make_secret(password):
    salt = os.urandom(4)
    sha = hashlib.sha1(password.encode('utf-8'))
    sha.update(salt)
    b64_digest_salt = b64encode(sha.digest() + salt).strip()
    return '{SSHA}' + b64_digest_salt.decode('utf-8')

def dn2rdns(dn):
    rdns = {}
    r = ldap.dn.str2dn(dn)
    for rdn in r:
        (a,v,t) = rdn[0]
        rdns.setdefault(a, []).append(v)
    return rdns

def find_cos(c, service):
    cos = {}
    r = c.search(None, "(&(objectClass=organization)(labeledURI={}))".format(service), ['o','dnQualifier','description'])
    for dn, entry in r:
        rdns = dn2rdns(dn)
        j = entry.get('description', None)
        description = {}
        if j:
            try:
                description = json.loads(j[0].decode())
            except Exception as e:
                print("find_cos: {}".format(e))
        if entry.get('dnQualifier', None):
            cos[rdns['o'][0]] = entry['dnQualifier']
        elif description.get('comanage_id', None):
            cos[rdns['o'][0]] = [description['comanage_id'].encode()]
        else:
            cos[rdns['o'][0]] = entry['o']
    return cos

def find_services(c):
    services = []
    r = c.search(None, '(&(objectClass=organization)(labeledURI=*))', ['labeledURI'])
    for dn, entry in r:
        services.extend(entry['labeledURI'])
    return list(set(services))

def find_clients(c, services):
    clients = {}
    for service in services:
        service = service.decode()
        clients[service] = []
        cos = find_cos(c, service)
        for co in cos.items():
            clients[service].append(co)
    return clients
