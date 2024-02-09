import json
import os
from time import time as now

import boto3


MAX_CONCURRENT_LAMBDAS = 2

env_name = os.environ['env_name']
arn_prefix = 'arn:aws:lambda'


def lambda_name_from_arn(arn: str):
    arn_parts = arn.split(':')
    return arn_parts[-2]


# Last stable, keys are numbers
lambdas_name_to_arn = {
    lambda_name_from_arn(lambda_arn): lambda_arn
    for _, lambda_arn in os.environ.items()
    if lambda_arn.startswith(arn_prefix)
}

# lambdas_name_to_arn = {
#     lambda_name_from_arn(lambda_arn): lambda_arn
#     for lambda_arn in os.environ.get('targets')
# }


def metric_for(func_name):
    return {
        'Namespace': 'AWS/Lambda',
        'MetricName': 'ConcurrentExecutions',
        'Dimensions': [
            {'Name': 'FunctionName', 'Value': func_name},
            {'Name': 'Resource', 'Value': f'{func_name}:{env_name}'}
        ]
    }


def get_max_metric_result(metric):
    print(f'metric is {metric}')
    results = metric['MetricDataResults'][0]
    values = results['Values']

    return min(int(max(values)) if len(values) > 0 else 1, MAX_CONCURRENT_LAMBDAS)


cloudwatch = boto3.client('cloudwatch')
lambda_client = boto3.client('lambda')


def inow():
    return int(now())


payload = json.dumps({'is_test_payload_to_warm_lambda': True})


def _warm_function_predictive(lambda_name: str, lambda_arn: str):
    """Triggers a dumb execution of a lambda to keep it warm.
    Calculates how many executions happened in the last 5 minutes and predicts how many instances should be kept warm.

    Not used since it's an overkill for now.
    """
    five_min_ago = inow() - 5 * 60
    end = inow()

    # get concurrency value
    metric_id = 'concurrent_executions'
    result = cloudwatch.get_metric_data(
        MetricDataQueries=[
            dict(Id=metric_id, MetricStat=dict(Metric=metric_for(lambda_name), Period=60, Stat='Maximum'))
        ],
        StartTime=five_min_ago, EndTime=end)
    concurrency_value = get_max_metric_result(result)
    print(f'concurrency for {lambda_name} is {concurrency_value}')

    # invoke async for _ in range(concurrency_value)
    for _ in range(concurrency_value):
        lambda_client.invoke(FunctionName=lambda_arn, Payload=payload, InvocationType='Event')


def _warm_function(lambda_name: str, lambda_arn: str):
    """Triggers a single execution of the lambda to keep it warm for the next 5min.
    """
    print(f'Warming {lambda_name}')
    lambda_client.invoke(FunctionName=lambda_arn, Payload=payload, InvocationType='Event')


def resolver(_, __):
    for lambda_name, lambda_arn in lambdas_name_to_arn.items():
        _warm_function(lambda_name, lambda_arn)
