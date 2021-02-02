# PLSC, a Python implementation of LSC

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
    sbs:
src:
  host: https://sbs.example.net
  user: sysread
  passwd: changethispassword
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

# Testing

For local testing, you need a local LDAP to be started before running tests.
When you have docker installed on your local machine, you can simple run:

```
etc/ldap_start.sh
```

This script will take care of pulling the proper LDAP image, start the docker container and initialize it properly with all required objectclasses.

If you do not have docker installed or wish to use an existing running LDAP server, then please make sure that the config files listed in **etc/ldif** are properly installed.

You can specify LDAP connection and access constants in a local **.env** file, for exanple:

```
DAP_URL="ldap://localhost:389"
LDAP_ADMIN_PASSWORD="secret"
LDAP_CONFIG_PASSWORD="config"
LDAP_DOMAIN="sram.tld"
LDAP_BASE_DN="dc=sram,dc=tld"
LDAP_BIND_DN="cn=admin,dc=sram,dc=tld"

SBS_URL=https://sbs.example.com
SBS_USER=sysread
SBS_PASS=secret
SBS_API_RECORDING=Yes
```

You have the option to run against an operational instance of SBS by specifing the **SBS_URL** and **SBS_USER** /**SBS_PASS** constants as shown above. If you do not want to access an SBS instance, just leave these constant out.
In that case the SBS API's are immitated by the results listed in the local **api** directory of this repository.

In case you are testing against an operational SBS instance, you have the option to record the API results for later use during mockup testing, just set the environment variable **SBS_API_RECORDING** to "Yes". Now the API requests results will be stored in the local directory under **./api/...**

When you omit the **SBS_URL** variable, the tests will run API requests agains the contents off this local **./api/...** directory

When all these preperations are completed, you can now run the tests:

```
pytest -v
```

After each Test cycle the contents of the LDAP can be inspected, for that run this command:

```
etc/ldap_show.sh
```

When finished you can tear down the local running LDAP instance, by:

```
etc/ldap_stop.sh

```

