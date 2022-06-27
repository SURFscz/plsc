import pyscim
from pyscim.api import user_api
from pyscim.model.name import Name
from pyscim.model.email import Email
from pyscim.model.user_resource import UserResource
from pprint import pprint

class AWSException(Exception):
    pass


class AWS(object):

    def __init__(self, config):
        aws_config = pyscim.Configuration(host=config.get('host', 'localhost'))
        aws_config.access_token = config.get('token', None)
        client = pyscim.ApiClient(aws_config)
        self.api = user_api.UserApi(client)

    def _parse_user(self, user):
        given_name = user.get('given_name', None)
        family_name = user.get('family_name', None)
        email = user.get('email', None)
        id = user.get('id', None)
        user_resource = UserResource()
        user_resource.external_id = user.get('external_id', None)
        user_resource.user_name = user.get('user_name', None)
        user_resource.display_name = user.get('display_name', None)
        user_resource.active = user.get('active', True)
        if id:
            user_resource.id = id
        if given_name or family_name:
            user_resource.name = Name(family_name=family_name, given_name=given_name)
        if email:
            user_resource.emails = [Email(value=email, primary=True)]

        return user_resource

    def list_users(self):
        try:
            api_response = self.api.get_users()
            return api_response
        except pyscim.ApiException as e:
            print("Exception when calling UserApi->list_users: %s\n" % e)

    def delete_user(self, id):
        try:
            api_response = self.api.delete_user_by_id(id)
            return api_response
        except pyscim.ApiException as e:
            print("Exception when calling UserApi->delete_user: %s\n" % e)

    def create_user(self, user):
        user_resource = self._parse_user(user)
        try:
            api_response = self.api.create_user(user_resource)
            return api_response
        except pyscim.ApiException as e:
            print("Exception when calling UserApi->create_user: %s\n" % e)

    def update_user(self, user, id):
        user_resource = self._parse_user(user)
        try:
            api_response = self.api.update_user_by_id(id, user_resource)
            return api_response
        except pyscim.ApiException as e:
            print("Exception when calling UserApi->update_user: %s\n" % e)
