import ldap, ldap.modlist

class Connection(object):

    # Connection parameters
    uri =None
    binddn = None
    passwd = None

    # LDAP connection
    c = None

    # BaseDN
    basedn = None

    def __init__(self, config):
        self.basedn = config['basedn']
        uri = config['uri']
        binddn = config['binddn']
        passwd = config['passwd']

        self.c = ldap.initialize(uri)
        self.c.simple_bind_s(binddn, passwd)

    def search(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        if not basedn:
            basedn = self.basedn
        return self.c.search_s(basedn, scope, fltr, attrs)

    def find(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        dns = {}
        try:
            r = self.search(basedn, fltr, attrs, scope)
            for dn, entry in r:
                dns[dn] = entry
        except Exception as e:
            print("find: {}".format(e))
        return dns

    def rfind(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        if basedn:
            b = "{},{}".format(basedn, self.basedn)
        else:
            b = self.basedn
        return self.find(b, fltr, attrs, scope)

    def add(self, dn, entry):
        addlist = ldap.modlist.addModlist(entry)
        try:
            self.c.add_s(dn, addlist)
        except Exception as e:
            pass
            #print(e)
        return addlist

    def modify(self, dn, old_entry, new_entry):
        modlist = ldap.modlist.modifyModlist(old_entry, new_entry)
        try:
            self.c.modify_s(dn, modlist)
        except Exception as e:
            pass
            #print(e)
        return modlist

    def delete(self, dn):
        return self.c.delete_s(dn)

    def get_sequence(self, dn):
        seq = 1000
        r = self.c.search_s(dn, ldap.SCOPE_BASE)
        for dn, old_entry in r:
            new_entry = old_entry.copy()
            seq = int(new_entry['serialNumber'][0].decode()) + 1
            new_entry['serialNumber'] = [ str(seq).encode() ]
            self.modify(dn, old_entry, new_entry)
        return seq
