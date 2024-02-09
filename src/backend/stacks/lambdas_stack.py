import importlib
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
from typing import List

from aws_cdk import (core,
                     aws_lambda as lambda_,
                     aws_iam as iam,
                     aws_events,
                     aws_events_targets, )

from src.backend import with_env, env_name, is_production_env
from src.backend.dataclasses import LayerConfig, LayerAppConfig, ResolverConfig
from src.backend.resources.handler_append import generate_append
from src.backend.resources.handler_prepend import generate_prepend

INSTALL_REQUIREMENTS = False  # Set this to True whenever you update your App's requirements.txt, keep False to cache


class LambdasStack(core.Construct):
    current_dir = os.path.split(os.path.abspath(__file__))[0]
    build_dir = os.path.join(current_dir, '..', '.build')

    resources_dir = os.path.join(current_dir, '..', 'resources')

    lambdas_dir = os.path.join(build_dir, 'lambdas')

    handler_file = 'resolver.py'  # This is what gets zipped and uploaded as the lambda content
    handler = 'resolver.resolver'  # What gets executed (`resolver` function from `resolver` file, see handler_apend)

    def __init__(self,
                 scope: core.Construct,
                 id_: str,
                 functions_config: List[ResolverConfig],
                 ):
        super().__init__(scope, id_)

        self.shared_layer = self._build_layer(LayerConfig(
            name='shared',
            # You can define multiple layers and install specific requirements into each
            requirements=[
                'base'  # This will install `requirements.base.txt` in this layer
            ],
            apps=[
                LayerAppConfig('your_app', copy_all=True),  # Your Django apps
            ],
            packages=['psycopg2', 'django_serverless'],
        ))

        self.lambdas_role = self._build_lambda_role()

        for config in functions_config:
            self._create_lambda_code_from_source(config)
            self._build_function(config)

        if is_production_env():
            print('Is production ENV, adding warmer function')
            lambda_warmer = self._build_warmer_function(functions_config)

            every_3_minutes = ','.join(map(str, list(range(0, 60, 3))))
            business_hours = ','.join(map(str, list(range(8, 23))))
            event = aws_events.Rule(self, with_env('lambda_warmer_rule'),
                                    schedule=aws_events.Schedule.cron(
                                        hour=business_hours,
                                        minute=every_3_minutes)
                                    )
            event.add_target(aws_events_targets.LambdaFunction(lambda_warmer))

    def _build_warmer_function(self, functions_config: List[ResolverConfig]):
        lambda_name = 'lambda_warmer'
        lambda_dir = os.path.join(self.resources_dir, lambda_name)
        # TODO: pass the stack ARN and use CloudFormation and Lambda SDKs to read all the lambdas in this stack
        # has to be a Dict because it's how the ARN is passed as a token, no serialization

        # Last stable, keys are numbers
        warmer_environment = {
            f'f{i}': config.function.function_arn
            for i, config in enumerate(functions_config)
        }

        return lambda_.Function(self, with_env(lambda_name),
                                runtime=lambda_.Runtime.PYTHON_3_8,
                                code=lambda_.Code.from_asset(lambda_dir),
                                handler='lambda_warmer.resolver',
                                function_name=with_env(lambda_name),
                                layers=[],
                                timeout=core.Duration.seconds(30),
                                role=self.lambdas_role,
                                memory_size=192,
                                environment=warmer_environment
                                )

    def _build_function(self, config: ResolverConfig):
        function = lambda_.Function(self, with_env(f'resolver-{config.name}'),
                                    runtime=lambda_.Runtime.PYTHON_3_8,
                                    code=lambda_.Code.from_asset(self.lambda_dir),
                                    handler=self.handler,
                                    function_name=with_env(config.name),
                                    layers=[self.shared_layer],
                                    timeout=core.Duration.seconds(15),
                                    role=self.lambdas_role,
                                    memory_size=192,
                                    )

        alias = lambda_.Alias(self, with_env(f'alias-{config.name}'),
                              alias_name=env_name(),
                              # TODO: figure a way for updating the version when a layer changes
                              # TODO: right now if we change the layer version and don't change the function code,
                              # TODO: the alias points to the previous version with the old layer version
                              version=function.current_version,
                              )
        config.function = alias

    def _prepare_lambda_directory(self, config: ResolverConfig):
        self.lambda_dir = os.path.join(self.lambdas_dir, config.name)
        os.makedirs(self.lambda_dir, exist_ok=True)

    def _create_lambda_code_from_source(self, config: ResolverConfig):
        self._prepare_lambda_directory(config)

        source_path = importlib.util.find_spec(config.path).origin
        if not os.path.exists(source_path):
            raise ValueError(
                f'Handler path {source_path} doesnt exists! Setup was probably done incorrectly and the deploy app cant find the code!')

        handler_path = os.path.join(self.lambda_dir, self.handler_file)

        with open(handler_path, 'wb') as handler_file:
            handler_file.write(generate_prepend(config))

            with open(source_path, 'rb') as source_file:
                handler_file.write(source_file.read())

            handler_file.write(generate_append(config))

    def _build_lambda_role(self):
        # TODO: make the IAM roles configurable per resolver
        function_name = 'lambdas'
        role = iam.Role(
            self, with_env(f'{function_name}-execution-role'),
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name=with_env(f'{function_name}-execution-role'),
        )
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-secrets-policy'),
            statements=[
                self._build_policy_statement(['secretsmanager:GetSecretValue']),
                self._build_policy_statement(['secretsmanager:ListSecrets']),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-logs-policy'),
            statements=[
                self._build_policy_statement([
                    'logs:CreateLogGroup',
                    'logs:CreateLogStream',
                    'logs:PutLogEvents',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-vpc-policy'),
            statements=[
                self._build_policy_statement([
                    'ec2:CreateNetworkInterface',
                    'ec2:DescribeNetworkInterfaces',
                    'ec2:DeleteNetworkInterface',
                    'ec2:AssignPrivateIpAddresses',
                    'ec2:UnassignPrivateIpAddresses',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-rds-policy'),
            statements=[
                self._build_policy_statement([
                    'rds:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-dynamodb-policy'),
            statements=[
                self._build_policy_statement([
                    'dynamodb:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-s3-policy'),
            statements=[
                self._build_policy_statement([
                    's3:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-lambda-policy'),
            statements=[
                self._build_policy_statement([
                    'lambda:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-events-policy'),
            statements=[
                self._build_policy_statement([
                    'events:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-cloudwatch-policy'),
            statements=[
                self._build_policy_statement([
                    'cloudwatch:GetMetricData',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-ses-policy'),
            statements=[
                self._build_policy_statement([
                    'ses:*',
                ]),
            ]
        ))
        role.attach_inline_policy(iam.Policy(
            self, with_env(f'{function_name}-rekognition-policy'),
            statements=[
                self._build_policy_statement([
                    'rekognition:*',
                ]),
            ]
        ))
        return role

    @staticmethod
    def _build_policy_statement(actions):
        return iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=actions,
            resources=['*']
        )

    def _build_layer(self, layer_config: LayerConfig):
        layer_name = layer_config.name

        layer_output_dir = os.path.join(self.build_dir, 'layers', layer_name)
        os.makedirs(layer_output_dir, exist_ok=True)
        layer_content_dir = os.path.join(layer_output_dir, 'python')

        if INSTALL_REQUIREMENTS:
            self._copy_requirements_to_layer(layer_content_dir, layer_config.requirements)

        self._copy_packages_to_layer(layer_content_dir, layer_config.packages)

        self._copy_settings_to_layer(layer_content_dir)

        for app_config in layer_config.apps:
            self._copy_app_to_layer(layer_content_dir, app_config)

        layer_id = with_env(f'layer-{layer_name}')
        layer_code = lambda_.Code.from_asset(layer_output_dir)

        return lambda_.LayerVersion(self, layer_id, code=layer_code)

    def _copy_requirements_to_layer(self, layer_content_dir, requirements):
        for requirements_name in requirements:
            requirements_file = os.path.abspath(
                os.path.join(self.current_dir, f'requirements.{requirements_name}.txt'))

            subprocess.check_call(
                f'python3 -m pip install -r {requirements_file} -t {layer_content_dir}'.split()
            )

    def _copy_settings_to_layer(self, layer_output_dir):
        import your_project as source_module
        source_module_dir = os.path.split(os.path.abspath(source_module.__file__))[0]

        layer_module_dir = os.path.join(layer_output_dir, 'your_project')
        os.makedirs(layer_module_dir, exist_ok=True)

        self._copy_files(source_module_dir, layer_module_dir, ['__init__.py', 'settings.py', 'wsgi.py', 'views.py'])
        self._copy_directories(source_module_dir, layer_module_dir, ['urls'])

    def _copy_app_to_layer(self, layer_content_dir, app_config):
        source_dir = self._get_app_source_dir(app_config.name)
        layer_module_dir = os.path.join(layer_content_dir, app_config.name)

        if app_config.copy_all:
            self._copy_directory(source_dir, layer_module_dir)
            return

        self._copy_files(source_dir, layer_module_dir, app_config.files)
        self._copy_directories(source_dir, layer_module_dir, app_config.modules)

    def _copy_packages_to_layer(self, layer_content_dir, packages):
        source_dir = os.path.join(self.resources_dir, 'packages')

        self._copy_directories(source_dir, layer_content_dir, packages)

    def _get_app_source_dir(self, app_name):
        app_module = importlib.import_module(app_name)
        return os.path.split(os.path.abspath(app_module.__file__))[0]

    @staticmethod
    def _copy_files(src_dir, dst_dir, files):
        os.makedirs(dst_dir, exist_ok=True)
        for file in files:
            source_file = os.path.join(src_dir, file)
            if not os.path.isfile(source_file):
                continue

            shutil.copyfile(source_file, os.path.join(dst_dir, file))

    def _copy_directories(self, src_dir, dst_dir, directories):
        for directory in directories:
            source_dir = os.path.join(src_dir, directory)
            if not os.path.isdir(source_dir):
                continue

            self._copy_directory(source_dir, os.path.join(dst_dir, directory))

    @staticmethod
    def _copy_directory(src_dir, dst_dir):
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
