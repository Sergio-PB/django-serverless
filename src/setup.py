import setuptools


with open('README.md') as fp:
    readme_content = fp.read()


setuptools.setup(
    name='django-serverless',
    version='0.0.1',

    description='',
    long_description=readme_content,
    long_description_content_type='text/markdown',

    author='Sérgio PB',

    install_requires=[
        'python-decouple==3.5',
        'aws-cdk.core==1.85.0',
        'aws-cdk.aws_lambda==1.85.0',
        'aws-cdk.aws_appsync==1.85.0',
        'aws-cdk.aws_apigateway==1.85.0',
        'aws-cdk.aws_applicationautoscaling==1.85.0',
        'aws-cdk.aws_cloudwatch==1.85.0',
        'aws-cdk.aws_events==1.85.0',
        'aws-cdk.aws_events_targets==1.85.0',
        'Django==3.0.8',
        'graphene==2.1.8',
        'graphene-django==2.15.0',
    ],

    python_requires='>=3.6',

    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Developers',

        'Programming Language :: Python :: 3 :: Only',

        'Topic :: Infrastructure as Code',

        'Typing :: Typed',
    ],
)
