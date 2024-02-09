from src.backend.dataclasses import ResolverConfig

__content = r'''
""" HANDLER PREPEND START """


import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')

django.setup(set_prefix=False)

from django.conf import settings
settings.CONN_MAX_AGE = PERSISTENT_CONNECTION


""" HANDLER PREPEND END """


'''


def generate_prepend(config: ResolverConfig):
    return __content \
        .replace('PERSISTENT_CONNECTION', '60' if config.persist_model_connection is None else 'None') \
        .encode('utf-8')
