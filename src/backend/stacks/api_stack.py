import os
from typing import List

from aws_cdk import (core,
                     aws_appsync as appsync,
                     aws_apigateway as apigateway)
from django.core.management import call_command

from src.backend import with_env
from src.backend.dataclasses import ResolverConfig

GENERATE_SCHEMA = True


class ApiStack(core.Construct):
    current_dir = os.path.split(os.path.abspath(__file__))[0]
    build_dir = os.path.join(current_dir, '..', '.build')

    resources_dir = os.path.join(current_dir, '..', 'resources')
    schema_path = os.path.join(resources_dir, 'schema.graphql')
    handler_prepend_path = os.path.join(resources_dir, 'handler_prepend.py')

    lambdas_dir = os.path.join(build_dir, 'lambdas')

    handler_file = 'resolver.py'
    handler = 'resolver.resolver'

    def __init__(self,
                 scope: core.Construct,
                 id_: str,
                 resolvers_config: List[ResolverConfig],
                 ):
        super().__init__(scope, id_)

        self._create_graphql_api()
        self.rest_resources = {}
        self._create_rest_api()

        self._create_resolvers(resolvers_config)

    def _create_rest_api(self):
        self.rest_api = apigateway.RestApi(
            self, with_env('rest-api'),
            rest_api_name=with_env('rest-api'),
            api_key_source_type=apigateway.ApiKeySourceType.HEADER,
            binary_media_types=['multipart/form-data'],
        )

    def _create_graphql_api(self):
        if GENERATE_SCHEMA:
            call_command('graphql_schema', '--schema', 'your_project.schema.schema', '--out', self.schema_path)
            self._clean_schema()

        self.graphql_api = appsync.GraphqlApi(
            self, with_env('api'),
            name=with_env('api'),
            schema=appsync.Schema.from_asset(self.schema_path),
            authorization_config=appsync.AuthorizationConfig(
                default_authorization=appsync.AuthorizationMode(
                    authorization_type=appsync.AuthorizationType.API_KEY,
                    api_key_config=appsync.ApiKeyConfig(name=with_env('appsync-api-key'))
                ),
            )
        )

    def _create_resolvers(self, resolvers_config):
        # TODO: create a service role for all data sources
        for resolver in resolvers_config:
            if resolver.operation in ['Query', 'Mutation']:
                data_source_name = with_env(f'{resolver.name}-source')
                data_source = appsync.LambdaDataSource(
                    self, data_source_name,
                    api=self.graphql_api,
                    lambda_function=resolver.function,
                    name=data_source_name.replace('-', '_')
                )
                appsync.Resolver(
                    self, with_env(f'{resolver.name}-resolver'),
                    api=self.graphql_api,
                    data_source=data_source,
                    field_name=resolver.name,
                    type_name=resolver.operation,
                )
            else:
                full_path_resources = resolver.rest_path.split('/')
                resource, resource_path = self._get_rest_resource(resolver)

                while resource_path != resolver.rest_path:
                    is_first_resource = resource_path == ''
                    current_path_position = 0 if is_first_resource else len(resource_path.split('/'))
                    next_resource = full_path_resources[current_path_position]

                    resource = resource.add_resource(
                        next_resource
                    )
                    resource_path = '/'.join([resource_path, next_resource]) if not is_first_resource else next_resource

                    self.rest_resources[resource_path] = resource

                resource.add_method(
                    resolver.operation,
                    apigateway.LambdaIntegration(
                        resolver.function,
                    )
                )

    def _get_rest_resource(self, resolver: ResolverConfig):
        if (full_path := resolver.rest_path) in self.rest_resources:
            return self.rest_resources[full_path], full_path

        path_parts = resolver.rest_path.split('/')
        full_path_len = len(resolver.rest_path.split('/'))
        for count in range(1, full_path_len):
            if (path := '/'.join(path_parts[:-count])) in self.rest_resources:
                return self.rest_resources[path], path

        return self.rest_api.root, ''

    def _clean_schema(self):
        with open(self.schema_path, 'r') as schema:
            content = schema.read()

        with open(self.schema_path, 'w') as schema:
            schema.write(content
                         .replace('UUID', 'ID')
                         .replace(' Date', ' AWSDate')
                         .replace('Decimal', 'Float')
                         .replace('scalar GenericScalar', '')
                         .replace('GenericScalar', 'AWSJSON'))
