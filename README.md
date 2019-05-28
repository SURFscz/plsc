# PLSC, a Python implemention of LSC

This project is a Python implementation aiming for LDAP to LDAP synchronization. We are inspired by the LSC project (https://lsc-project.org/doku.php)

## Install

For local development we advice to make use of Pythion Virtual Environment. The installation commands are specified below.

## Sample Syncronisation script

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
