#!/usr/bin/env python3
from sbs import SBS
from aws import AWS
import sys
import yaml
from pprint import pprint


with open(sys.argv[1]) as f:
   config = yaml.safe_load(f)

src = SBS(config['sbs']['src'])
aws = AWS(config['aws'])
co = config['aws']['co']

'''
new_user = {
    'id': '9067453ca5-978ddc27-a48a-4acf-abd8-9edd2571f247',
    'external_id': 'c7c7f2c1ee3a469558cd64942b86fbc4273abfa2',
    'user_name': 'c7c7f2c1ee3a469558cd64942b86fbc4273abfa2@sram.surf.nl',
    'display_name': 'Martin van Es',
    'active': True,
    'given_name': 'Martin',
    'family_name': 'van Es',
    'email': 'martin.vanes@surf.nl'
}

#aws.create_user(new_user)
aws.update_user(new_user, '9067453ca5-978ddc27-a48a-4acf-abd8-9edd2571f247')
pprint(result)
exit(0)
'''

my_co = src.collaboration(co)
co_users = {}
for membership in my_co['collaboration_memberships']:
    user = membership['user']
    #pprint(user)
    user_id = f"{user['id']}"
    name = user['name']
    email = user['email']
    uid = user['uid']
    if 'Doe' not in name or True:
        co_users[user_id] = {
            'uid': uid,
            'name': name,
            'email': email
        }

users = aws.list_users()
aws_users = {}
for user in users.resources:
    id = user.id
    display_name = user.display_name
    external_id = user.external_id
    user_name = user.user_name
    aws_users[external_id] = {
        'id': id,
        'display_name': display_name,
        'user_name': user_name
    }

for external_id, co_user in co_users.items():
    user = {
        'active': True,
        'external_id': external_id,
        'user_name': co_user['email'],
        'display_name': co_user['name'],
        'given_name': co_user['name'],
        'family_name': co_user['name'],
        'email': co_user['email']
    }
    if external_id in aws_users:
        print(f'update {external_id}')
        aws_id = aws_users[external_id]['id']
        user['id'] = aws_id
        aws.update_user(user, aws_id)
        aws_users.pop(external_id)
    else:
        print(f'create {external_id}')
        aws.create_user(user)
    pprint(user)

for external_id, aws_user in aws_users.items():
    print(f'delete {external_id}')
    pprint(aws_user)
    aws.delete_user(aws_user['id'])

users = aws.list_users()
print('Remaining users')
for user in users.resources:
    id = user.id
    display_name = user.display_name
    print(f'{id}: {display_name}')
