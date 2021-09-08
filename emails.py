#!/usr/bin/env python3

import sys
import yaml
import json
from datetime import datetime
from sbs import SBS

if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

src = SBS(config['sbs']['src'])


print("SRAM prod contacts generated "+datetime.now().isoformat())
print("type:Name:id:role:email")

organisations = src.organisations()
#print(json.dumps(organisations, indent=2))
#exit()

for organisation in organisations:
    id = organisation['id']
    org = src.organisation(id)
    name = org['name']
    #print(json.dumps(org, indent=2))
    #print(f"Organisation: {name}")
    for user in org['organisation_memberships']:
        role = user['role']
        mail = user['user']['email']
        print(f"org,{id},{name},org-{role},{mail}")

services = src.services()
#print("\nServices")
#print(json.dumps(organisations, indent=2))

for service in services:
    id = service['id']
    srvc = src.service(id)
    #print(json.dumps(srvc, indent=2))
    name = srvc['name']
    mail = srvc['contact_email']
    print(f"service,{id},{name},sp-contact,{mail}")

collaborations = src.collaborations()
#print("\nCollaborations")
#print(json.dumps(collaborations, indent=2))

for collaboration in collaborations:
    id = collaboration['id']
    col = src.collaboration(id)
    if col is None or not col: 
        next
    #print(json.dumps(col, indent=2))
    name = col.get('name','-')
    for user in col['collaboration_memberships']:
        role = user['role']
        mail = user['user']['email']
        if role == 'admin':
            print(f"co,{id},{name},co-{role},{mail}")
