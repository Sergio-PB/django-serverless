import base64
import io
import json
import re
from cgi import FieldStorage
from dataclasses import dataclass, field
from datetime import datetime, date
from types import GeneratorType
from typing import Dict, Optional, List, Any, Callable
from uuid import UUID

import graphene
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.http.response import HttpResponseBase, JsonResponse
from django.utils.module_loading import import_string

import graphene_extender
from graphene_extender.classes import ReverseModelTypeMeta


class ResponseHolder(HttpResponseBase):
    def __init__(self, content: Any):
        super().__init__(status=200, content_type='text/plain', charset='utf-8')
        self.content = content
        self.streaming = False


@dataclass
class RequestHolder:
    user: Optional[Dict]
    headers: Dict
    META: Dict
    method: str
    body: str
    path: str
    path_info: str
    _get_raw_host: Callable
    get_full_path: Callable
    COOKIES: Dict = field(default_factory=dict)
    FILES: Dict = field(default_factory=dict)

    def get_host(self):
        return HttpRequest.get_host(self)


@dataclass
class ValueHolder:
    value: Any


@dataclass
class SelectionHolder:
    name: ValueHolder
    alias: ValueHolder


@dataclass
class SelectionSetHolder:
    selections: List[SelectionHolder]


@dataclass
class OperationDefinitionHolder:
    operation: str
    selection_set: SelectionSetHolder


@dataclass
class ResolveInfoHolder:
    path: List[str]
    context: RequestHolder
    field_name: str
    operation: OperationDefinitionHolder


@dataclass
class PromiseLikeHolder:
    reason: Any
    value: Any
    is_rejected: bool
    is_fulfilled: bool


class AttrDict(dict):
    """This converts the input dict to an object with attributes."""

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def get(self, key, default=None):
        if default is None:
            return self[key]

        value = self[key]
        return default if value is None else value

    def __getattr__(self, attr):
        return super(AttrDict, self).get(attr)


class CaseInsensitiveDict(dict):
    @classmethod
    def _k(cls, key):
        return key.lower() if isinstance(key, str) else key

    def __init__(self, *args, **kwargs):
        super(CaseInsensitiveDict, self).__init__(*args, **kwargs)
        self._convert_keys()

    def __getitem__(self, key):
        return super(CaseInsensitiveDict, self).__getitem__(self.__class__._k(key))

    def __setitem__(self, key, value):
        super(CaseInsensitiveDict, self).__setitem__(self.__class__._k(key), value)

    def __delitem__(self, key):
        return super(CaseInsensitiveDict, self).__delitem__(self.__class__._k(key))

    def __contains__(self, key):
        return super(CaseInsensitiveDict, self).__contains__(self.__class__._k(key))

    def pop(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).pop(self.__class__._k(key), *args, **kwargs)

    def get(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).get(self.__class__._k(key), *args, **kwargs)

    def setdefault(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).setdefault(self.__class__._k(key), *args, **kwargs)

    def update(self, E=None, **F):
        super(CaseInsensitiveDict, self).update(self.__class__(E))
        super(CaseInsensitiveDict, self).update(self.__class__(**F))

    def _convert_keys(self):
        for k in list(self.keys()):
            v = super(CaseInsensitiveDict, self).pop(k)
            self.__setitem__(k, v)


# TODO: initialize middlewares in Lambda context and not execution
def wrap_handler_with_middlewares(initial_request_handler):
    chained_handler = initial_request_handler

    for middleware_path in reversed(settings.MIDDLEWARE):

        middleware = import_string(middleware_path)

        def printme(mid, txt):
            print(txt, str(mid))

            def aux(*a, **kw):
                return mid(*a, **kw)

            return aux

        middleware.__call__ = printme(middleware.__call__, 'running handler (django) middleware ')
        wrapped_handler = printme(middleware, 'initializing ')(chained_handler)

        if wrapped_handler is None:
            raise ImproperlyConfigured(
                'Middleware factory %s returned None.' % middleware_path
            )

        chained_handler = wrapped_handler
    print('ended wrapping handler')
    return chained_handler


class RequestWrapper:
    def __init__(self):
        self.initial_request_hook = lambda: None


request_wrapper = RequestWrapper()


# This ensures the request_wrapper.initial_request_hook is defined after lambda executed
def run_request_wrapper_hook(*args, **kwargs):
    return request_wrapper.initial_request_hook(*args, **kwargs)


handler_with_middlewares = wrap_handler_with_middlewares(run_request_wrapper_hook)


def execute_resolver_with_middlewares(initial_request_resolver):
    print('starting execute_resolver_with_middlewares')

    def wrap_as_promise(resolver):
        def promise_like_resolver(*args, **kwargs):
            returned_promise_like = PromiseLikeHolder(is_rejected=False, reason=None, is_fulfilled=True, value=None)

            try:
                result = resolver(*args, **kwargs)
            except Exception as e:
                returned_promise_like.reason = e
                returned_promise_like.value = e
                returned_promise_like.is_rejected = True
                returned_promise_like.is_fulfilled = False
            else:
                returned_promise_like.reason = result
                returned_promise_like.value = result

            return returned_promise_like

        return promise_like_resolver

    print('before wrapping as promise')
    last_resolver = wrap_as_promise(initial_request_resolver)
    print('after wrapping as promise')

    for middleware_path in settings.GRAPHENE.get('MIDDLEWARE', []):
        middleware = import_string(middleware_path)()

        def wrapped_resolver(clojure_middleware, clojure_last_resolver):
            def clojure_resolver(*args, **kwargs):
                print('running resolver (graphene) middleware ', clojure_middleware)
                return clojure_middleware.resolve(clojure_last_resolver, *args, **kwargs)

            return clojure_resolver

        last_resolver = wrapped_resolver(middleware, last_resolver)
    print('after middleware loop')

    def unwrap_from_promise(resolver):
        def resolver_that_returns_promise(*args, **kwargs):
            promise_like_dict = resolver(*args, **kwargs)

            if promise_like_dict.is_rejected:
                raise promise_like_dict.reason

            return promise_like_dict.value

        return resolver_that_returns_promise

    print('ending execute_resolver_with_middlewares')

    return unwrap_from_promise(last_resolver)


camel_to_snake_pattern = re.compile(r'(?<!^)(?=[A-Z])')


def camel_to_snake(name: str):
    return camel_to_snake_pattern.sub('_', name).lower()


def snake_to_camel(name: str):
    first, *others = name.split('_')
    return ''.join([first.lower(), *map(str.title, others)])


def resolve_fields(instance, type_: Optional[type], selection_set, info):
    if instance is None:
        return None

    return_dict = {}

    for field_name in selection_set:
        if field_name == '__typename':
            return_dict[field_name] = type_.__name__ if type_ is not None else None
            continue

        if '/' in field_name:
            continue

        subfield_prefix = f'{field_name}/'
        subset = [
            sub_selection[len(subfield_prefix):]
            for sub_selection in selection_set
            if sub_selection.startswith(subfield_prefix)
        ]

        field_name_snake_case = camel_to_snake(field_name)

        def default_resolver(i, _):
            # If it's a dict, just return the value under its key
            if isinstance(i, dict):
                return i.get(field_name_snake_case)

            # In case the type_ is actually the model and not the type, we reverse access the type and get the resolver
            if hasattr(i, ReverseModelTypeMeta.REVERSE_ATTR_NAME):
                graphene_type = getattr(i, ReverseModelTypeMeta.REVERSE_ATTR_NAME)
                if (graphene_resolver := getattr(graphene_type, f'resolve_{field_name_snake_case}', None)) is not None:
                    return graphene_resolver(i, _)

            if hasattr(i, field_name_snake_case):
                return getattr(i, field_name_snake_case)

            return lambda _, __: None

        def serialize_value(value):
            if isinstance(value, UUID):
                return str(value)

            if isinstance(value, datetime):
                return value.strftime('%Y-%m-%dT%H:%M:%SZ')

            if isinstance(value, date):
                return value.strftime('%Y-%m-%d')

            if isinstance(value, GeneratorType):
                return list(value)

            return value

        field_value = getattr(type_, f'resolve_{field_name_snake_case}', default_resolver)(instance, info)

        if len(subset) == 0:
            return_dict[field_name] = serialize_value(field_value)
        else:
            if field_value is None:
                return_dict[field_name] = None
                continue

            if field_value.__class__.__name__ in ('RelatedManager', 'ManyRelatedManager'):
                field_value = field_value.all()

            # TODO: get child type somewhere
            child_type = None
            if field_value.__class__.__name__ in ('ManyRelatedManager', 'QuerySet', 'list'):
                return_dict[field_name] = [
                    resolve_fields(child, child_type, subset, info)
                    for child in field_value
                ]
            else:
                return_dict[field_name] = resolve_fields(field_value, child_type, subset, info)

    return return_dict


def return_none_if_is_warmup(f):
    def wrapped_lambda(event, _context):
        if event.get('is_test_payload_to_warm_lambda', False):
            print('is a lambda warmer event, returning None')
            return None

        print('not a warmer event, running lambda')
        return f(event, _context)

    return wrapped_lambda


def apigateway_to_wsgi(resolver):
    # TODO: move this to a new file `apigateway_to_wsgi.py`
    @return_none_if_is_warmup
    def apigateway_handler(event, _context):
        event_headers = CaseInsensitiveDict(event.get('headers', {}))
        event_path = event.get('path', '')
        event_info = event.get('info', {})
        event_body = event.get('body', '')
        event_params = event.get('pathParameters', {})
        if event_params is None:
            event_params = {}
        event_method = event.get('httpMethod', 'POST')
        content_type_header = event_headers.get('Content-Type', '')

        fs: Optional[FieldStorage] = None
        if content_type_header.startswith('multipart/'):
            raw_body = base64.b64decode(event_body)
            # body = raw_body.decode('iso-8859-1')
            fs = FieldStorage(fp=io.BytesIO(raw_body), headers=event_headers,
                              environ={'REQUEST_METHOD': event_method, 'CONTENT_TYPE': content_type_header, })['file']

        wsgi_request = RequestHolder(
            user=None,
            headers=event_headers,
            META=event_headers,
            FILES={} if fs is None else {'file': fs},
            method=event_method,
            body=str(event_info),
            path=event_path,
            path_info=event_path,
            _get_raw_host=lambda: f'{event_headers["host"]}:{event_headers["x-forwarded-port"]}',
            get_full_path=lambda: event_path,
        )

        def request_handler(request):
            result = resolver(request, **event_params)

            if isinstance(result, JsonResponse):
                result = {
                    'statusCode': 200,
                    'body': '{}',
                    **json.loads(result.content)
                }

            response_holder_content: Any

            response_holder_object = ResponseHolder(result)
            response_holder_object._headers = event_headers

            return response_holder_object

        response_holder: ResponseHolder = wrap_handler_with_middlewares(request_handler)(wsgi_request)
        return response_holder.content

    return apigateway_handler


def appsync_to_wsgi_of(graphene_type, is_list=False, is_paginated=False, input_type=None):
    def appsync_to_wsgi(resolver):
        @return_none_if_is_warmup
        def appsync_handler(event, _context):
            print('starting appsync handler')
            event_headers = event.get('request', {}).get('headers', {})
            event_info = event.get('info', {})

            wsgi_request = RequestHolder(
                user=None,
                headers=event_headers,
                META=event_headers,
                method='POST',
                body=str(event_info),
                path='/graphql',
                path_info='/graphql',
                _get_raw_host=lambda: f'{event_headers["host"]}:{event_headers["x-forwarded-port"]}',
                get_full_path=lambda: '/graphql',
            )

            field_name = event_info.get('fieldName')

            root = None if event_info.get('parentTypeName').lower() in ['query', 'mutation'] else True
            arguments = event.get('arguments', {})
            arguments = {
                camel_to_snake(key): arguments[key]
                for key in arguments
            }

            if 'input' in arguments:
                input_dict = arguments['input']
                snake_case_input_dict = {camel_to_snake(key): value for key, value in input_dict.items()}

                arguments['input'] = AttrDict(**snake_case_input_dict)
                if input_type is not None:
                    if hasattr(input_type, 'model'):
                        AttrDict.model = input_type.model
                        AttrDict.fields = input_type.fields
                        AttrDict.to_model = graphene_extender.classes.InputFactory.to_model

                    for input_field_name, raw_value in snake_case_input_dict.items():
                        if raw_value is None:
                            continue

                        if isinstance(getattr(input_type, input_field_name), graphene.types.Date):
                            arguments['input'][input_field_name] = datetime.strptime(raw_value, '%Y-%m-%d').date()

            def request_handler(request):
                print('starting appsync request handler')
                selection_set_fields = event_info.get('selectionSetList', [])
                info = ResolveInfoHolder(
                    path=[field_name],
                    context=request,
                    field_name=field_name,
                    operation=OperationDefinitionHolder(
                        operation=event_info.get('parentTypeName', '').lower(),
                        selection_set=SelectionSetHolder(selections=[])
                    ),
                )

                result = execute_resolver_with_middlewares(resolver)(root, info, **arguments)

                response_holder_content: Any

                if is_list:
                    response_holder_content = [
                        resolve_fields(instance, graphene_type, selection_set_fields, info)
                        for instance in result
                    ]

                elif is_paginated:
                    selection_set_fields = [
                        selection_field.replace('data/', '') if selection_field.startswith('data/') else selection_field
                        for selection_field in selection_set_fields
                        if selection_field not in ['data', 'total_results', 'totalResults']
                    ]
                    data = [
                        resolve_fields(instance, graphene_type, selection_set_fields, info)
                        for instance in result.data
                    ]
                    response_holder_content = {'data': data, 'totalResults': result.total_results}

                else:
                    response_holder_content = resolve_fields(result, graphene_type, selection_set_fields, info)

                response_holder_object = ResponseHolder(response_holder_content)
                response_holder_object._headers = event_headers

                return response_holder_object

            print('sending response through pipeline')
            request_wrapper.initial_request_hook = request_handler
            response_holder: ResponseHolder = handler_with_middlewares(wsgi_request)
            return response_holder.content

        return appsync_handler

    return appsync_to_wsgi
