# Makefile

all: pytest

image:
	docker build -t plsc .

ldap_start:
	etc/ldap_start.sh

ldap_show:
	etc/ldap_show.sh

ldap_stop:
	etc/ldap_stop.sh

pytest: image ldap_start
	docker run --rm -ti --network host -v ${PWD}:/app plsc pytest
