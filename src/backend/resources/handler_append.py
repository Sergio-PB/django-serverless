from src.backend.dataclasses import ResolverConfig

__query_content = r'''
""" HANDLER APPEND START """

MODEL_CONNECTION

from django_serverless.appsync_to_wsgi import appsync_to_wsgi_of

resolver = appsync_to_wsgi_of(TYPENAME, is_list=IS_LIST, is_paginated=IS_PAGINATED)(resolver)

""" HANDLER APPEND END """


'''

__mutation_content = r'''
""" HANDLER APPEND START """

MODEL_CONNECTION

from django_serverless.appsync_to_wsgi import appsync_to_wsgi_of

resolver = appsync_to_wsgi_of(TYPENAME, input_type=INPUT_TYPE)(TYPENAME.mutate)

""" HANDLER APPEND END """


'''

__rest_content = r'''
""" HANDLER APPEND START """

MODEL_CONNECTION

from django_serverless.appsync_to_wsgi import apigateway_to_wsgi

resolver = apigateway_to_wsgi(TYPENAME)

""" HANDLER APPEND END """


'''


def generate_append(config: ResolverConfig):
    if config.operation in ['GET', 'POST']:
        content = __rest_content
    else:
        is_mutation = config.operation == 'Mutation'
        content = __mutation_content if is_mutation else __query_content

    return content \
        .replace('TYPENAME', config.graphene_type) \
        .replace('IS_LIST', str(config.is_list)) \
        .replace('IS_PAGINATED', str(config.is_paginated)) \
        .replace('INPUT_TYPE', str(config.input_type)) \
        .replace('MODEL_CONNECTION',
                 '' if config.persist_model_connection is None else
                 f'{config.persist_model_connection}.objects.first()') \
        .encode('utf-8')
