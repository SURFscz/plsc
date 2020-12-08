#!/usr/bin/env python3

import sys
import yaml
import json
from sbs import SBS

if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

src = SBS(config['sbs']['src'])


organisations = src.organisations()
print("\nOrganisations")
#print(json.dumps(organisations, indent=2))
#exit()

for organisation in organisations:
    org = src.organisation(organisation['id'])
    name = org['name']
    #print(json.dumps(org, indent=2))
    print(f"Organisation: {name}")
    for user in org['organisation_memberships']:
        role = user['role']
        mail = user['user']['email']
        print(f"{role}: {mail}")

services = src.services()
print("\nServices")
#print(json.dumps(organisations, indent=2))

for service in services:
    srvc = src.service(service['id'])
    #print(json.dumps(srvc, indent=2))
    name = srvc['name']
    mail = srvc['contact_email']
    print(f"Service: {name}")
    print(f"contact: {mail}")

collaborations = src.collaborations()
print("\nCollaborations")
#print(json.dumps(collaborations, indent=2))

for collaboration in collaborations:
    col = src.collaboration(collaboration['id'])
    #print(json.dumps(col, indent=2))
    name = col['name']
    print(f"Collaboration: {name}")
    for user in col['collaboration_memberships']:
        role = user['role']
        mail = user['user']['email']
        if role == 'admin':
            print(f"{role}: {mail}")
