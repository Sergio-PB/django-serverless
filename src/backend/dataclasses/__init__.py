import os
from dataclasses import dataclass, field
from typing import List

from aws_cdk import aws_lambda


def _default_files_factory():
    return [
        '__init__.py',
        'documents.py',
        'apps.py',
        'admin.py',
        'urls.py',
        'views.py',
    ]


def _default_modules_factory():
    return [
        'models',
        os.path.join('graphql', 'types'),
        'views',
        'dataclasses',
        'middlewares',
        'enums',
        'functions',
        'services',
        'sso',
        'signals',
        'urls',
        'views',
        'templates',
        'decorators',
    ]


@dataclass
class LayerAppConfig:
    name: str = field()
    copy_all: bool = field(default=False)
    files: List[str] = field(default_factory=_default_files_factory)
    modules: List[str] = field(default_factory=_default_modules_factory)


@dataclass
class LayerConfig:
    name: str = field()
    packages: List[str] = field(default_factory=list)
    apps: List[LayerAppConfig] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)


@dataclass
class ResolverConfig:
    name: str = field()
    graphene_type: str = field()
    operation: str = field()
    path: str = field()
    function: aws_lambda.Alias = field(init=False)
    is_list: bool = field(default=False)
    is_paginated: bool = field(default=False)
    input_type: str = field(default='None')
    rest_path: str = field(default='')
    scale_on_usage: bool = field(default=False)
    persist_model_connection: str = field(default=None)
