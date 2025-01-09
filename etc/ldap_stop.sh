#!/bin/bash

# Set CONTAINER_TOOL to 'docker' if not defined
CONTAINER_TOOL=${CONTAINER_TOOL:-docker}

# Kill previous server
$CONTAINER_TOOL stop my-ldap
