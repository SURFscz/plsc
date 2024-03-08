#!/usr/bin/env python
import sys
import yaml
import json

from sbs import SBS


def main():
    if len(sys.argv) < 2:
        sys.exit(sys.argv[0] + "  <conf.yml>")

    with open(sys.argv[1]) as f:
        config = yaml.safe_load(f)

    src = SBS(config['sbs']['src'])
    sync = src.api("api/plsc/sync")

    print(json.dumps(sync, indent=2))


if __name__ == "__main__":
    main()
