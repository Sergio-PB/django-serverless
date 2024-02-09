# Hello! This is very much under construction. 🏗️

## Overview
What started as an AWS CDK template is turning into a serverless deployer for Django projects.
The goal is to provide a blueprint to build and deploy a Django app with AWS serverless components. From here onwards,
let's refer to the Django app as *App*.

The end result of this deployer is to be able to auto-digest a Django project as long as it follows standard naming 
conventions (e.g. `models/__init__.py` or `models.py` to hold model classes).

This current version is tightly coupled with a lot of things. AWS as a provider should be abstracted for example.

The deployer will digest the App's source code and generate AWS CloudFormation resources. Resources used are:
* Stacks - the following CloudFormation stacks are used to organize and manage the AWS resources
  * BackendStack - holds all resources
    * Here is where you perform the mapping of which views you want to expose in your ApiStack
    * LambdasStack - holds the App's views as lambda resolvers (deployed in versions and aliases)
    * ApiStack - holds the ApiGateway and AppSync resources
* ApiGateway - standard Django urls are mapped to ApiGateway resources
* AppSync - GraphQL APIs developed with graphene/django-graphene generate an AppSync API (the schema is auto-generated 🪄)
* Lambda - all the views are deployed as lambda resolvers
* CloudWatch - a rule to fire a "lambda warmer" event to avoid the lambda startup overhead latency


### Why?
The vision behind this project is to support developers on building the good ol' Django  monolith and using 
Infrastructure-as-Code to deploy in a fast and modular manner, an elastic infrastructure for their application.


### Deployer's features

* Multiple environments
  * You can deploy versions of your App across several environments (see `src/backend/__init__.py`)
* Warming up lambdas
  * Configurable to a business hours window to reduce costs, 24h for availability, or any in between
* Cached and persistent DB connections
  * Configure your API resolvers to keep DB connections open with `ResolverConfig.persist_model_connection`
  * See `PERSISTENT_CONNECTION` in `src/backend/resources/handler_prepend.py`
  * See `MODEL_CONNECTION` in `src/backend/resources/handler_append.py`
* LambdaLayers
  * Optimize as granular as you want, which code lives in which Lambda resolver and share code with shared layers
  * See `shared_layer` in `src/backend/stacks/lambdas_stack.py`
* GraphQL schema generation
  * You don't have to write your schema; graphene provides a schema generation command which the deployer will use
  * Set `GENERATE_SCHEMA = True` in `src/backend/stacks/api_stack.py`
* Custom static dependencies
  * If you use a python package that can't be installed easily on the fly with pip, you can include the dependencies in `src/backend/resources/packages`
  * E.g. See `src/backend/resources/packages/psycopg2`


### Which App can I use?
The deployed app should be a standard Django MVT app. With URLs, migrations, middlewares and any other layers (services,
DRF classes, utilities, ...).


### Blueprint overview
During the deployment, the source code of your views have to be zipped and uploaded as a Lambda source code. For this 
process to happen correctly, your App should (at the moment) be setup with the following:
* Have a single function/class per file

Here's an example of an App `your_project` with a Django app `your_app`
```bash
src
├── manage.py
├── your_project
│   ├── __init__.py
│   ├── asgi.py
│   ├── schema.py
│   ├── settings.py
│   ├── urls
│   │   ├── api_urls.py
│   │   └── urls.py
│   ├── views.py
│   └── wsgi.py
├── your_app
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── enums
│   ├── graphql
│   │   ├── __init__.py
│   │   ├── mutations
│   │   │   ├── __init__.py
│   │   │   └── graphql_mutation.py
│   │   ├── queries
│   │   │   ├── __init__.py
│   │   │   └── graphql_query.py
│   │   ├── schema.py
│   │   └── types
│   │       ├── __init__.py
│   │       └── model_type.py
│   ├── migrations
│   │   ├── 0001_initial.py
│   │   └── __init__.py
│   ├── models
│   │   ├── __init__.py
│   │   └── model.py
│   ├── services
│   │   ├── __init__.py
│   │   └── service.py
│   ├── signals
│   │   ├── __init__.py
│   │   └── signal.py
│   ├── urls.py
│   └── views
│       ├── __init__.py
│       └── rest_view.py
├── requirements.txt
├── dependency_app
│   ├── __init__.py
│   ├── dataclasses
│   ├── enums
│   ├── functions
│   ├── migrations
│   ├── models
│   ├── services
│   └── types.py
```

---

## Setting up and running it

While the deployer is in construction, the instructions and the code here **are not stable**.

Nonetheless, what you have to do is:

1. Install the requirements in your virtual environment:

```
$ pip install -r requirements.txt
```

2. Configure your project references and expose your endpoints
   1. Search for `your_project` and replace with your App's reference
   2. Configure the IaC files:
      * `src/backend/backend_stack.py`
      * `src/backend/stacks/api_stack.py`
      * `src/backend/stacks/lambdas_stack.py`

3. And synthesize and deploy the CloudFormation template generated.

```
$ cdk deploy
```

Enjoy!
