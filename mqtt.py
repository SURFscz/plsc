#!/usr/bin/env python3

import sys
import yaml
import json
import socket
import traceback

import mqtt_util
import mqtt_flat
from mqtt_util import mqttClient
from sldap import sLDAP
from sbs import SBS

if len(sys.argv) < 2:
    sys.exit(sys.argv[0] + "  <conf.yml>")

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

src = SBS(config['sbs']['src'])
dst = sLDAP(config['ldap']['dst'])
mqtt_topic = config['mqtt']['topic']


def service(method, action, msg):
    sid = int(msg['id'])
    print(f"handling service {method} {action} {sid}")
    if method == 'post':
        mqtt_util.create_service(src, dst, config, sid)
    elif method == 'put':
        mqtt_util.update_service(src, dst, config, sid)
    elif method == 'delete':
        mqtt_util.delete_service(dst, msg)
    return False


def collaboration(method, action, msg):
    if action == "collaborations/invites":
        print(f"discarding collaborations invites msg")
        return
    cid = int(msg['id'])
    print(f"handling collaboration {method} {action} {cid} {msg}")
    if method == 'post':
        mqtt_util.create_collaboration(src, dst, config, cid)
    elif method == 'put':
        mqtt_util.update_collaboration(src, dst, config, cid)
    elif method == 'delete':
        mqtt_util.delete_collaboration(dst, cid)
    return cid


def collab_service(method, action, msg):
    cid = int(msg['collaboration_id'])
    sid = int(msg['service_id'])
    print(f"handling collaboration service {method} {action} s:{sid} c:{cid} {msg}")
    if method == 'delete':
        mqtt_util.remove_collaboration(src, dst, cid, sid)
    else:
        mqtt_util.create_collaboration(src, dst, config, cid)
    return cid


def collab_member(method, action, msg):
    print(f"handling collaboration membership {method} {action} {msg}")
    cid = int(msg['collaboration_id'])
    uid = int(msg['user_id'])
    if method == 'delete':
        mqtt_util.clean_collaboration(src, dst, cid)
    else:
        mqtt_util.collab_member(src, dst, config, cid, uid)
    return cid


def invitation(method, action, msg):
    cid = False
    if action == 'invitations/accept' and method == 'put':
        print(f"handling invitations {method} {action} {msg}")
        cid = int(msg['collaboration_id'])
        uid = int(msg['user_id'])
        mqtt_util.create_user(src, dst, config, cid, uid)
    else:
        print(f"discarding invitations {method} {action} {msg}")
    return cid


def join_request(method, action, msg):
    cid = False
    if action == 'join_requests/accept' and method == 'put':
        print(f"handling join_request {method} {action} {msg}")
        cid = int(msg['collaboration_id'])
        uid = int(msg['user_id'])
        mqtt_util.create_user(src, dst, config, cid, uid)
    else:
        print(f"discarding join_request {method} {action} {msg}")
    return cid


def group(method, action, msg):
    print(f"handling group {method} {action} {msg}")
    cid = int(msg['collaboration_id'])
    gid = int(msg['id'])
    if method == "delete":
        mqtt_util.delete_group(src, dst, cid, gid, msg)
    else:
        mqtt_util.create_group(src, dst, cid, gid)
    return cid


def group_member(method, action, msg):
    print(f"handling group_member {method} {action} {msg}")
    cid = int(msg['collaboration_id'])
    if method == "delete":
        gid = int(msg['id'])
        mqtt_util.remove_group_users(src, dst, config, cid, gid)
    else:
        gid = int(msg['group_id'])
        mqtt_util.group_users(src, dst, config, cid, gid)
    return cid


def unknown(method, action, msg):
    print(f"don\'t know what to do with {method} {action} {msg}")
    return False


def on_message(message):
    print("-")
    switcher = {
        'services': service,
        'collaborations': collaboration,
        'collaborations_services': collab_service,
        'collaboration_memberships': collab_member,
        'groups': group,
        'group_members': group_member,
        'invitations': invitation,
        'join_requests': join_request,
    }
    topic = message.topic
    method = topic.rsplit('/', 1)[-1]
    action = topic[8:].rsplit('/', 1)[0]
    subject = action.split('/')[0]
    msg = json.loads(message.payload.decode("utf-8"))

    func = switcher.get(subject, unknown)
    try:
        cid = func(method, action, msg)
        if cid:
            # This misses deleted services for cid
            # As flatten loops over services for cid
            # It also misses deleted CO's
            mqtt_flat.flatten(dst, dst, src, cid)
    except Exception as e:
        traceback.print_exc()


def main():
    mqtt = mqttClient(config['mqtt'])

    while True:
        msg = mqtt.subscribe(mqtt_topic)
        on_message(msg)


if __name__ == "__main__":
    # execute only if run as a script
    main()