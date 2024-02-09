from aws_cdk import core

from . import with_env
from .dataclasses import ResolverConfig
from .stacks.api_stack import ApiStack
from .stacks.lambdas_stack import LambdasStack


class BackendStack(core.Stack):
    """Base Stack that holds all resources and CDK constructs.


    # Example of a Users app configuration

    functions_config = [
        # Looking up users and login in are very frequent, so no it's good to keep an open DB connection
        ResolverConfig(
            'user',  # resolver name
            'UserType',  # resolver return type
            'Query',  # Operation type, either 'Query' | 'Mutation'
            'users.graphql.queries.user',  # resolver function file reference
            persist_model_connection='UserModel',  # which model class to use to keep the connection open
        ),
        ResolverConfig(
            'login',
            'Login',
            'Mutation',
            'users.graphql.mutations.login',
            persist_model_connection='User',
        ),
        # The logout is not that frequent, so no need to keep an open DB connection
        ResolverConfig('logout', 'Logout', 'Mutation', 'users.graphql.mutations.logout'),

        # Resolvers for REST endpoints
        ResolverConfig(
            'uploadProfileImage',  # resolver name
            'UploadProfileImageApi.post',  # resolver function reference
            'POST',
            'users.views.upload_profile_image',  # resolver function file reference
            rest_path='api/users/{user_id}/profile-image'
        ),
        ResolverConfig('confirmUserWeb', 'ConfirmUserApi.get', 'GET',
                       'users.views.confirm_user',
                       rest_path='api/users/{user_id}/confirm-user/{code}'),
    ]
    """

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        functions_config = [
            # A runnable example, replace with your resolvers
            ResolverConfig('user', 'UserType', 'Query', 'users.graphql.queries.user',
                           persist_model_connection='UserModel'),
        ]

        self.lambdas_stack = LambdasStack(self, with_env('lambdas-stack'), functions_config)
        ApiStack(self, with_env('api-stack'), functions_config)
