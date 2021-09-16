#!/usr/bin/env python3

import sys
import yaml
from datetime import datetime
from sbs import SBS


if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

src = SBS(config['sbs']['src'])

print("SRAM prod contacts generated " + datetime.now().isoformat())
print("type:Name:id:role:email")

organisations = src.organisations()
#print(json.dumps(organisations, indent=2))
#exit()

for organisation in organisations:
    o_id = organisation['id']
    org = src.organisation(o_id)
    name = org['name']
    #print(json.dumps(org, indent=2))
    #print(f"Organisation: {name}")
    for user in org['organisation_memberships']:
        role = user['role']
        mail = user['user']['email']
        print(f"org,{o_id},{name},org-{role},{mail}")

services = src.services()
#print("\nServices")
#print(json.dumps(organisations, indent=2))

for service in services:
    s_id = service['id']
    srvc = src.service(s_id)
    #print(json.dumps(srvc, indent=2))
    name = srvc['name']
    mail = srvc['contact_email']
    print(f"service,{s_id},{name},sp-contact,{mail}")

collaborations = src.collaborations()
#print("\nCollaborations")
#print(json.dumps(collaborations, indent=2))

for collaboration in collaborations:
    c_id = collaboration['id']
    col = src.collaboration(c_id)
    if col is None or not col:
        continue
    #print(json.dumps(col, indent=2))
    name = col.get('name', '-')
    for user in col['collaboration_memberships']:
        role = user['role']
        mail = user['user']['email']
        if role == 'admin':
            print(f"co,{c_id},{name},co-{role},{mail}")
