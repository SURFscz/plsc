# PLSC, a Python implementation of LSC

This project is a Python implementation aiming for LDAP to LDAP synchronization. We are inspired by the LSC project (https://lsc-project.org/doku.php)

## Install

For local development we advice to make use of Python Virtual Environment. The installation commands are specified below.

## Sample Synchronisation configuration

This is an example of what we need to specify source and destination.
[ More complex examples will follow ]

```bash
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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Use

`sync_services` will look for all `labeledURI` attributes in the source and create `dc=<labeledURI>` branches on the destination containing all CO's that are linked to these services with bare `People`, `Groups` and `uid/gidNumberSequence` structures.

`plsc` will then mirror all `People` and `Groups` to the corresponding CO's in the destination LDAP, optionally converting attributes and dn's as defined in the code on the way:

```bash
            # Here's the magic: Build the new person entry
            dst_entry = {}
            dst_entry['objectClass'] = ['inetOrgPerson', 'person', 'posixAccount']
            dst_entry['uid'] = [src_uid]
            dst_entry['cn'] = src_entry['cn']
            dst_entry['sn'] = src_entry['sn']
            dst_entry['homeDirectory'] = ['/home/{}'.format(src_uid)]
```

And for groups:

```bash
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

```bash
etc/ldap_start.sh
```

This script will take care of pulling the proper LDAP image, start the docker container and initialize it properly with all required objectclasses.

If you do not have docker installed or wish to use an existing running LDAP server, then please make sure that the config files listed in **etc/ldif** are properly installed.

You can specify LDAP connection and access constants in a local **.env** file, for exanple:

```bash
LDAP_URL="ldap://localhost:389"
LDAP_ADMIN_PASSWORD="secret"
LDAP_CONFIG_PASSWORD="config"
LDAP_DOMAIN="sram.tld"
LDAP_BASE_DN="dc=sram,dc=tld"
LDAP_BIND_DN="cn=admin,dc=sram,dc=tld"

SBS_URL=https://sbs.example.com
SBS_USER=sysread
SBS_PASS=secret
SBS_API_RECORDING=Yes
SBS_VERIFY_SSL=Yes
```

You have the option to run against an operational instance of SBS by specifing the **SBS_URL** and **SBS_USER** /**SBS_PASS** constants as shown above. If you do not want to access an SBS instance, just leave these constant out.
In that case the SBS API's are immitated by the results listed in the local **api** directory of this repository.

In case you are testing against an operational SBS instance, you have the option to record the API results for later use during mockup testing, just set the environment variable **SBS_API_RECORDING** to "Yes". Now the API requests results will be stored in the local directory under **./api/...**

When you omit the **SBS_URL** variable, the tests will run API requests agains the contents off this local **./api/...** directory

When all these preperations are completed, you can now run the tests:

```bash
pytest -v
```

After each Test cycle the contents of the LDAP can be inspected, for that run this command:

```bash
etc/ldap_show.sh
```

When finished you can tear down the local running LDAP instance, by:

```bash
etc/ldap_stop.sh

```

# Using Make

A Makefile is added to make life easier. Now you can run:

```bash
make pytest
```

Or just make. This will build the docker image and run pytest next.

```bash
make
```

# Docker

A Dockerfile is added to produce an image that is capable of running PLSC. Since PLSC depends on an input YAML file holding the source and destionatination details, you have to provide sucan YANL file.
Using Docker you can do the following:

Suppose you have prepared you YAML file (inspired by plsc.yml.example) and this file is 'my-plsc.yml'

You have to mount this file into the container and then run **run.sh** with that file as parameter.

Example:

```bash
docker run -v ${PWD}:/opt/plsc plsc ./run.sh my-plsc.yaml
```

If you started the local LDAP via **etc/ldap_start.sh** then you can connect to that if you run this PLSC container in **network = host** mode.

```bash
docker run -v ${PWD}:/opt/plsc --network host plsc ./run.sh my-plsc.yaml
```

**run.sh** is the existing script that runs both _plsc_ordered.py_ and _plsc_flat_
