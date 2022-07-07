import ldap
import ldap.modlist
import logging


class SLdap(object):

    # LDAP connection, private
    __c = None

    # BaseDN, public
    basedn = None

    def __init__(self, config):
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, 0)
        ldap.set_option(ldap.OPT_X_TLS_DEMAND, True)

        self.basedn = config['basedn']
        uri = config['uri']
        binddn = config['binddn']
        passwd = config['passwd']

        self.sizelimit = int(config.get('sizelimit', 500))

        logging.debug("[LDAP] Initializing ldap: {}, sizelimit: {}".format(uri, self.sizelimit))
        self.__c = ldap.initialize(uri)

        if binddn == 'external':
            self.__c.sasl_external_bind_s()
        else:
            self.__c.simple_bind_s(binddn, passwd)

    @staticmethod
    def __encode(entry):
        r = {}
        for k, v in entry.items():
            rv = []
            for ev in v:
                rv.append(str(ev).encode('UTF-8'))
            r[k] = rv
        return r

    @staticmethod
    def __decode(entry):
        r = {}
        for k, v in entry.items():
            rv = []
            for ev in v:
                rv.append(str(ev.decode('UTF-8')))
            r[k] = rv
        return r

    def __search(self, basedn, ldap_filter='(ObjectClass=*)', attrs=None, scope=ldap.SCOPE_SUBTREE):
        logging.debug("[LDAP] Search: {}".format(basedn))

        if attrs is None:
            attrs = []
        if not basedn:
            basedn = self.basedn

        page_control = ldap.controls.SimplePagedResultsControl(True, size=self.sizelimit, cookie='')
        result = []

        while True:
            page = self.__c.search_ext(basedn, scope, ldap_filter, attrs, serverctrls=[page_control])
            _, rdata, _, serverctrls = self.__c.result3(page)

            result.extend(rdata)
            controls = [
                control for control in serverctrls
                if control.controlType == ldap.controls.SimplePagedResultsControl.controlType
            ]

            if not controls:
                logging.errror('The server ignores RFC 2696 control')
            if not controls[0].cookie:
                break

            #logging.debug("Paging ...")
            page_control.cookie = controls[0].cookie

        return result

    def find(self, basedn, ldap_filter='(ObjectClass=*)', attrs=None, scope=ldap.SCOPE_SUBTREE):
        dns = {}
        try:
            r = self.__search(basedn, ldap_filter, attrs, scope)
            for dn, entry in r:
                dns[dn] = self.__decode(entry)
        except ldap.NO_SUCH_OBJECT:
            # nothing found, just return an empty result
            return {}
        except ldap.NO_RESULTS_RETURNED as e:
            logging.error(f"find: {e} on filter '{ldap_filter}'")
            raise e
        return dns

    def rfind(self, basedn, ldap_filter='(ObjectClass=*)', attrs=None, scope=ldap.SCOPE_SUBTREE):
        if basedn:
            b = "{},{}".format(basedn, self.basedn)
        else:
            b = self.basedn
        return self.find(b, ldap_filter, attrs, scope)

    def add(self, dn, entry):
        addlist = ldap.modlist.addModlist(self.__encode(entry))
        try:
            logging.debug("[LDAP] Create: {}".format(dn))
            self.__c.add_s(dn, addlist)
        except Exception as e:
            logging.error(f"Exception on add of {dn}: {e}")
            logging.error(f"entry: {entry}")
            raise e
        return addlist

    def modify(self, dn, old_entry, new_entry):
        modlist = ldap.modlist.modifyModlist(self.__encode(old_entry), self.__encode(new_entry))
        if modlist:
            try:
                logging.debug("[LDAP] Modify: {}".format(modlist))
                self.__c.modify_s(dn, modlist)
            except Exception as e:
                logging.error(f"Exception on modify of {dn}: {e}")
                logging.error(modlist)
                raise e
        return modlist

    # store tries to add, then modifies if exists.
    def store(self, dn, new_entry):
        logging.debug("[LDAP] Store: {}".format(new_entry))

        dst_dns = self.find(dn, scope=ldap.SCOPE_BASE)
        if len(dst_dns) == 1:
            dn, entry = list(dst_dns.items())[0]
            return self.modify(dn, entry, new_entry)
        elif len(dst_dns) == 0:
            return self.add(dn, new_entry)
        else:
            return "Too many dn's This shouldn't happen"

    # A cheaper store
    def merge(self, dn, all_dns, old_entry, new_entry):
        logging.debug("[LDAP] Merge: {}".format(new_entry))
        if not old_entry:
            ldif = self.add(dn, new_entry)
        elif old_entry == new_entry:
            ldif = {}
        else:
            ldif = self.modify(dn, old_entry, new_entry)
        all_dns[dn] = new_entry
        return ldif

    def delete(self, dn):
        try:
            logging.debug("[LDAP] Delete: {}".format(dn))
            self.__c.delete_s(dn)
        except Exception as e:
            logging.error("{}\n  {}".format(dn, e))
            raise e

    def rdelete(self, dn):
        children = self.find(dn, scope=ldap.SCOPE_ONELEVEL)
        if len(children):
            for child_dn in children:
                self.rdelete(child_dn)
        self.delete(dn)

    def get_sequence(self, dn) -> int:
        seq = 1000
        r = self.__c.search_s(dn, ldap.SCOPE_BASE)
        for dn, old_entry in r:
            old_entry = self.__decode(old_entry)
            new_entry = old_entry.copy()
            seq = int(new_entry['serialNumber'][0]) + 1
            new_entry['serialNumber'] = [str(seq)]
            self.modify(dn, old_entry, new_entry)
        return seq
