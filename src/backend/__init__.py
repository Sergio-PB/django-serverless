from decouple import config

ENVIRONMENT_NAME = config('ENVIRONMENT_NAME', default='prod', cast=str)
DEBUG = config('DEBUG', default=False, cast=bool)
IS_PRODUCTION = config('IS_PRODUCTION', default=True, cast=bool)


def is_debug_env():
    """Even in a production-like environment (e.g. stage) we may want to have debug traces."""
    return DEBUG


def is_production_env():
    return IS_PRODUCTION


def env_name():
    return ENVIRONMENT_NAME


def with_env(name: str):
    return f'{name}-{ENVIRONMENT_NAME}'


from .backend_stack import BackendStack
