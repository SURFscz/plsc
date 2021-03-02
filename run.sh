#!/bin/bash

set -e

export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

if [ -z "$1" ]; then
  echo "No configuration given"
  exit 1
elif [ ! -f "$1" ]; then
  echo "configuration not found"
  exit 1
fi

/usr/bin/env python plsc_ordered.py "$1"
/usr/bin/env python plsc_flat.py "$1"
