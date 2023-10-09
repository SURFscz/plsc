#!/usr/bin/env python3

import sys
import csv
import logging
from io import TextIOBase

import yaml
import argparse
import datetime
from typing import List, Dict, Set
from sbs import SBS

contacts_type = List[Dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='List contacts from SBS.')
    parser.add_argument('--sbs', type=str, required=True,
                        help='config file containing SBS endpoints and credentials')

    org_group = parser.add_mutually_exclusive_group()
    org_group.add_argument('--org', default=True, action='store_true', help='Fetch org admins/managers (default: true)')
    org_group.add_argument('--no-org', dest='org', action='store_false', help=argparse.SUPPRESS)

    co_group = parser.add_mutually_exclusive_group()
    co_group.add_argument('--co', default=False, action='store_true', help='Fetch co admins (default: false)')
    co_group.add_argument('--no-co', dest='co', action='store_false', help=argparse.SUPPRESS)

    srvc_group = parser.add_mutually_exclusive_group()
    srvc_group.add_argument('--service', default=True, action='store_true', help='Fetch service contacts (default)')
    srvc_group.add_argument('--no-service', dest='service', action='store_false', help=argparse.SUPPRESS)

    parser.add_argument('--debug', default=False, action='store_true', help='Show debug information (default: false)')
    parser.add_argument('--format', choices=["csv", "xlsx", "email_list"], default="csv",
                        help="Type of output to produce (default: csv)")
    parser.add_argument('-o', '--output', default=sys.stdout, type=argparse.FileType('w'),
                        help="Type of output to produce (default: csv)")

    args = parser.parse_args()
    return args


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

    # sort contacts by type, id, role, name
    contacts.sort(key=lambda c: (c['type'], c['id'], c['role'], c['name']))

    return contacts


def write_csv(contacts: contacts_type, fd: TextIOBase = sys.stdout) -> None:
    w = csv.writer(fd, dialect="excel")
    columns = ("type", "id", "name", "role", "mail")
    w.writerow(columns)
    w.writerows([[c[key] for key in columns] for c in contacts])


def write_xls(contacts: contacts_type, fd: TextIOBase) -> None:
    try:
        import xlsxwriter
    except ImportError:
        print("Please install xlsxwriter: pip install xlsxwriter")
        sys.exit(1)

    # raw (binary) file buffer:
    raw_fd = fd.buffer

    workbook = xlsxwriter.Workbook(raw_fd, {'in_memory': True})
    workbook.set_properties({'created': datetime.date(2015, 10, 21)})
    worksheet = workbook.add_worksheet()

    columns = ("type", "id", "name", "role", "mail")
    columns_width = (8, 6, 30, 20, 30)

    row_max = len(contacts) + 1 - 1
    col_max = len(columns) - 1

    # write header
    for col_num, col_name in enumerate(columns):
        worksheet.write(0, col_num, col_name)
        # set column width
        worksheet.set_column(col_num, col_num, columns_width[col_num])

    # write data
    for row_num, data in enumerate(contacts):
        for col_num, col_name in enumerate(columns):
            logging.debug(f"{row_num + 1} {col_num} {col_name} {data[col_name]}")
            worksheet.write(row_num + 1, col_num, data[col_name] or "")
    logging.debug("Data written")

    # autofilter
    worksheet.autofilter(0, 0, row_max, col_max)

    logging.debug("Done!")

    workbook.close()


def main() -> None:
    args = parse_args()

    if args.debug:
        logging.basicConfig(level="DEBUG")
    else:
        logging.basicConfig(level="INFO")

    sbs = open_sbs(args.sbs)
    contacts = fetch_contacts(sbs, org=args.org, co=args.co, service=args.service)

    if args.format == 'csv':
        write_csv(contacts, fd=args.output)
    elif args.format == 'xlsx':
        write_xls(contacts, fd=args.output)
    elif args.format == 'email_list':
        # uniquify list of emails
        emails: Set[str] = set(c['mail'].lower() for c in contacts if c['mail'])
        print(args.output, *sorted(emails), sep="\n")


if __name__ == "__main__":
    main()
