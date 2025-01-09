# Makefile

# Include the .test.env file
include .test.env
export $(shell sed 's/=.*//' .test.env)

# Set CONTAINER_TOOL to 'docker' if not defined in .test.env
CONTAINER_TOOL ?= docker

all: pytest

image:
	$(CONTAINER_TOOL) build -t plsc .

ldap_start:
	etc/ldap_start.sh

ldap_show:
	etc/ldap_show.sh

ldap_stop:
	etc/ldap_stop.sh

pytest: image ldap_start
	$(CONTAINER_TOOL) run --rm -ti --network host --volume ${PWD}/api:/opt/plsc/api plsc pytest

clean: ldap_stop
