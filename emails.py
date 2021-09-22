#!/usr/bin/env python3

import sys
import getopt
import csv
import yaml
from typing import List, Dict
from datetime import datetime
from sbs import SBS


if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")


contacts_type = List[Dict[str, str]]


def open_sbs(plsc_config_file: str) -> SBS:
    with open(plsc_config_file) as f:
        config = yaml.safe_load(f)

    src = SBS(config['sbs']['src'])
    return src


def fetch_contacts(src: SBS, org: bool = True, co: bool = True, service: bool = True) -> contacts_type:
    contacts: contacts_type = []
    if org:
        organisations = src.organisations()
        for organisation in organisations:
            o_id = organisation['id']
            org = src.organisation(o_id)
            for user in org['organisation_memberships']:
                contacts.append({
                    "type": "org",
                    "id": o_id,
                    "name": org['name'],
                    "role": "org-" + user['role'],
                    "mail": user['user']['email']
                })

    if service:
        services = src.services()
        for service in services:
            s_id = service['id']
            srvc = src.service(s_id)
            contacts.append({
                "type": "service",
                "id": s_id,
                "name": srvc['name'],
                "role": "sp-contact",
                "mail": srvc['contact_email']
            })

    if co:
        collaborations = src.collaborations()
        for collaboration in collaborations:
            c_id = collaboration['id']
            col = src.collaboration(c_id)
            if col is None or not col:
                continue
            for user in col['collaboration_memberships']:
                role = user['role']
                if role == 'admin':
                    contacts.append({
                        "type": "co",
                        "id": c_id,
                        "name": col.get('name', '-'),
                        "role": "co-" + role,
                        "mail": user['user']['email']
                    })

    return contacts


def main() -> None:
    sbs = open_sbs(sys.argv[1])
    contacts = fetch_contacts(sbs)

    w = csv.writer(sys.stdout, dialect="excel")
    w.writerow(["SRAM prod contacts generated " + datetime.now().isoformat()])
    columns = ("type", "id", "name", "role", "mail")
    w.writerow(columns)
    w.writerows([[c[key] for key in columns] for c in contacts])


if __name__ == "__main__":
    main()
