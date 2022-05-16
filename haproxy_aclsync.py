#!/usr/bin/env python3

from typing import List, Dict, Set, Tuple, Union
import argparse
import ipaddress
import yaml
import haproxyadmin
from sbs import SBS


# parse arguments and read config file
def parse_args() -> Dict:
    parser = argparse.ArgumentParser(description='Sync Service IP ranges from SBS to haproxy ACLs')
    parser.add_argument('config', type=str,
                        help='config file containing SBS endpoints and credentials')

    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    return config


class HAProxyException(Exception):
    pass


# comprehensive object to interact with haproxy
class HAProxyACL:
    def __init__(self, config: Dict[str, str]):
        self._haproxy = haproxyadmin.haproxy.HAProxy(socket_file=config['socket'])
        self._acl_id = config['acl_file']

    def acl_file(self):
        return self._acl_id

    def get_acl(self) -> List[str]:
        raw_acls = self._haproxy.show_acl(self._acl_id)
        acls = [s.rpartition(' ')[2] for s in raw_acls]
        return acls

    def del_acl(self, acl: str):
        if not self._haproxy.del_acl(acl=self._acl_id, key=acl):
            raise HAProxyException(f"Couldn't delete acl `{acl}` from `{self._acl_id}`")

    def add_acl(self, acl: str):
        if not self._haproxy.add_acl(acl=self._acl_id, pattern=acl):
            raise HAProxyException(f"Couldn't add acl `{acl}` to `{self._acl_id}`")


# partition two sets
# returns tuple: (items unique to a, items unique to b, common items)
def partition_sets(a: Union[Set, List], b: Union[Set, List]) -> Tuple[Set, Set, Set]:
    unique_a = set(a)
    unique_b = set(b)
    common = set()

    for item in unique_a.copy():
        if item in unique_b:
            common.add(item)
            unique_a.discard(item)
            unique_b.discard(item)

    return unique_a, unique_b, common


# sort IP addresses
def sort_ips(ip: str) -> Tuple[int, Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    net = ipaddress.ip_network(ip)
    return net.version, net


def main() -> None:
    config = parse_args()
    debug = config.get("debug", False)

    sbs = SBS(config['sbs'])
    sbs_ipranges = sorted(sbs.service_ipranges())

    haproxy = HAProxyACL(config=config['haproxy'])
    haproxy_acl = haproxy.get_acl()

    unique_haproxy, unique_sbs, common = partition_sets(haproxy_acl, sbs_ipranges)
    if debug:
        print("haproxy only: ", unique_haproxy)
        print("sbs only: ", unique_sbs)
        print("common: ", common)

    # remove acls from haproxy that are no longer in SBS:
    for acl in unique_haproxy:
        print(f"Removing acl `{acl}`")
        haproxy.del_acl(acl)

    # add acls from SBS that are not yet in haproxy
    for acl in unique_sbs:
        print(f"Adding acl `{acl}`")
        haproxy.add_acl(acl)

    # write entire acl to file if anything changed
    if unique_sbs or unique_haproxy:
        with open(haproxy.acl_file(), "w") as acl_file:
            for acl in sorted(haproxy.get_acl(), key=sort_ips):
                print(acl, file=acl_file)


if __name__ == "__main__":
    main()
