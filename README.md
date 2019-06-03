# PLSC, a Python implemention of LSC

This project is a Python implementation aiming for LDAP to LDAP synchronization. We are inspired by the LSC project (https://lsc-project.org/doku.php)

## Install

For local development we advice to make use of Python Virtual Environment. The installation commands are specified below.

## Sample Synchronisation configuration

This is an example of what we need to specify source and destination.
[ More complex examples will follow ]

```
---
ldap:
  src:
    uri: ldap://ldap.vm.scz-vm.net
    basedn: dc=scz,dc=vnet
    binddn: cn=John Doe,dc=scz,dc=vnet
    passwd: changethispassword
  dst:
    uri: ldap://ldap.vm.scz-vm.net
    basedn: dc=clients,dc=vnet
    binddn: cn=admin,dc=clients,dc=vnet
    passwd: changethispassword
pwd: changethispassword
uid: 1000
gid: 1000
```

### Local development

Create a virtual environment and install the required python packages:
```
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Use
```sync_services``` will look for all ```labeledURI``` attributes in the source and create ```dc=<labeledURI>``` branches on the destination containing all CO's that are linked to these services with bare ```People```, ```Groups``` and ```uid/gidNumberSequence``` structures.

```plsc``` will then mirror all ```People``` and ```Groups``` to the corresponding CO's in the destination LDAP, optionally converting attributes and dn's as defined in the code on the way:
```
            # Here's the magic: Build the new person entry
            dst_entry = {}
            dst_entry['objectClass'] = ['inetOrgPerson', 'person', 'posixAccount']
            dst_entry['uid'] = [src_uid]
            dst_entry['cn'] = src_entry['cn']
            dst_entry['sn'] = src_entry['sn']
            dst_entry['homeDirectory'] = ['/home/{}'.format(src_uid)]
```

And for groups:
```
            # Here's the magic: Build the new group entry
            m = re.search('^(?:GRP)?(?:CO)?(?:COU)?:(.*?)$', src_cn)
            dst_cn = src_type + "_" + m.group(1) if m.group(1) else ""

            dst_entry = {}
            dst_entry['objectClass'] = ['extensibleObject', 'posixGroup', 'sczGroup']
            dst_entry['cn'] = [dst_cn]
            dst_entry['description'] = [src_cn]
```
