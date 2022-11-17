#!/usr/bin/env python3
import os
import sys
import yaml
import json
from sbs import SBS

api_dir = 'api'


def clean_dir(location):
    files = os.listdir(location)
    for entry in files:
        entry = os.path.realpath(os.path.join(location, entry))
        print(f"remove {entry}")
        if os.path.isdir(entry):
            clean_dir(entry)
            os.rmdir(entry)
        else:
            os.remove(entry)


def write_collaborations(location, src):
    os.mkdir(f"{location}/collaborations")

    # Find all CO's in SBS
    collaborations = src.collaborations()

    file = os.path.realpath(os.path.join(location, "collaborations/all"))
    with open(file, "w") as f:
        print(f"write {file}")
        f.write(json.dumps(collaborations, indent=2))

    for collaboration in collaborations:
        id = collaboration['id']
        file = os.path.realpath(os.path.join(location, "collaborations/" + str(id)))
        with open(file, "w") as f:
            print(f"write {file}")
            f.write(json.dumps(collaboration, indent=2))


def write_plsc(location, src):
    os.mkdir(f"{location}/plsc")

    # Find all CO's in SBS
    sync = src.api("api/plsc/sync")

    file = os.path.realpath(os.path.join(location, "plsc/sync"))
    with open(file, "w") as f:
        print(f"write {file}")
        f.write(json.dumps(sync, indent=2))


def main():

    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = SBS(config['sbs']['src'])

    clean_dir(api_dir)
    write_collaborations(api_dir, src)
    write_plsc(api_dir, src)


if __name__ == "__main__":
    main()
