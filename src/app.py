#!/usr/bin/env python3

import os
import sys

import django
from aws_cdk import core

from src.backend import with_env
from src.backend.backend_stack import BackendStack


def initialize_django_app():
    sys.path.append(os.path.abspath(os.path.join('..', 'src')))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'off_backend.settings')

    django.setup(set_prefix=False)


initialize_django_app()

app = core.App()
BackendStack(app, with_env('backend'))

app.synth()
