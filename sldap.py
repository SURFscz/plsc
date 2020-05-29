# -*- coding: future_fstrings -*-

import ldap, ldap.modlist

class sLDAP(object):

    # LDAP connection, private
    __c = None

    # BaseDN, public
    basedn = None

    def __init__(self, config):
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, 0)
        ldap.set_option( ldap.OPT_X_TLS_DEMAND, True )

        self.basedn = config['basedn']
        uri = config['uri']
        binddn = config['binddn']
        passwd = config['passwd']

        self.__c = ldap.initialize(uri)

        if binddn == 'external':
            self.__c.sasl_external_bind_s()
        else:
            self.__c.simple_bind_s(binddn, passwd)

    def __encode(self, entry):
        r = {}
        for k, v in entry.items():
            rv = []
            for ev in v:
                rv.append(str(ev).encode())
            r[k] = rv
        return r

    def __decode(self, entry):
        r = {}
        for k, v in entry.items():
            rv = []
            for ev in v:
                rv.append(str(ev.decode()))
            r[k] = rv
        return r

    def __search(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        if not basedn:
            basedn = self.basedn
        return self.__c.search_s(basedn, scope, fltr, attrs)

    def find(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        dns = {}
        try:
            r = self.__search(basedn, fltr, attrs, scope)
            for dn, entry in r:
                dns[dn] = self.__decode(entry)
        except Exception as e:
            #print("find: {}".format(e))
            pass
        return dns

    def rfind(self, basedn, fltr='(ObjectClass=*)', attrs=[], scope=ldap.SCOPE_SUBTREE):
        if basedn:
            b = "{},{}".format(basedn, self.basedn)
        else:
            b = self.basedn
        return self.find(b, fltr, attrs, scope)

    def add(self, dn, entry):
        addlist = ldap.modlist.addModlist(self.__encode(entry))
        try:
            self.__c.add_s(dn, addlist)
        except Exception as e:
            print("  {}: {}".format(e, dn))
        return addlist

    def modify(self, dn, old_entry, new_entry):
        modlist = ldap.modlist.modifyModlist(self.__encode(old_entry), self.__encode(new_entry))
        try:
            self.__c.modify_s(dn, modlist)
        except Exception as e:
            print("  {}: {}".format(e, dn))
        return modlist

    # store tries to add, then modifies if exists.
    def store(self, dn, new_entry):
        dst_dns = self.find(dn, scope=ldap.SCOPE_BASE)
        if len(dst_dns) == 1:
            dn, entry = list(dst_dns.items())[0]
            return self.modify(dn, entry, new_entry)
        elif len(dst_dns) == 0:
            return self.add(dn, new_entry)
        else:
            return "Too many dn's This shouldn't happen"

    def delete(self, dn):
        try:
            self.__c.delete_s(dn)
        except Exception as e:
            print("{}\n  {}".format(dn, e))

    def rdelete(self, dn):
        children = self.find(dn, scope=ldap.SCOPE_ONELEVEL)
        if len(children):
          for child_dn in children:
            self.rdelete(child_dn)
        self.delete(dn)

    def get_sequence(self, dn):
        seq = 1000
        r = self.__c.search_s(dn, ldap.SCOPE_BASE)
        for dn, old_entry in r:
            old_entry = self.__decode(old_entry)
            new_entry = old_entry.copy()
            seq = int(new_entry['serialNumber'][0]) + 1
            new_entry['serialNumber'] = [ str(seq) ]
            self.modify(dn, old_entry, new_entry)
        return seq
