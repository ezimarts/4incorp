"""Refresh counts and assign auxiliary numbers without changing primary keys."""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
counters = dynamodb.Table(os.environ['COUNTERS_TABLE'])
specs = json.loads(os.environ['TABLE_SPECS'])


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def conditional_failure(error):
    return error.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException'


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a sequence number')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or result != int(result):
        raise ValueError('Sequence numbers must be nonnegative integers')
    return int(result)


def is_legacy_counter(item, spec):
    legacy = spec.get('legacy_key')
    return bool(legacy and all(item.get(k) == v for k, v in legacy.items()))


def scan_records(table, spec):
    request = {'ConsistentRead': True}
    # Read keys and numeric fields only; no client names, documents or payment data.
    fields = sorted(set(spec['keys'] + [spec['number_attribute']]))
    aliases = {f'#f{i}': field for i, field in enumerate(fields)}
    request.update(ProjectionExpression=', '.join(aliases), ExpressionAttributeNames=aliases)
    while True:
        result = table.scan(**request)
        for item in result.get('Items', []):
            if not is_legacy_counter(item, spec):
                yield item
        if not result.get('LastEvaluatedKey'):
            return
        request['ExclusiveStartKey'] = result['LastEvaluatedKey']


def raise_floor(table_name, floor):
    try:
        counters.update_item(Key={'counter_name': table_name},
            UpdateExpression='SET last_assigned=:floor',
            ConditionExpression='attribute_not_exists(last_assigned) OR last_assigned < :floor',
            ExpressionAttributeValues={':floor': floor})
    except ClientError as error:
        if not conditional_failure(error):
            raise


def allocate(table_name):
    result = counters.update_item(Key={'counter_name': table_name},
        UpdateExpression='SET last_assigned=last_assigned+:one',
        ConditionExpression='attribute_exists(last_assigned)',
        ExpressionAttributeValues={':one': 1}, ReturnValues='UPDATED_NEW')
    return number(result['Attributes']['last_assigned'])


def reconcile_table(spec):
    table = dynamodb.Table(spec['table'])
    observed_at = now_iso()
    records = list(scan_records(table, spec))
    attribute = spec['number_attribute']
    floor = max([spec.get('start', 0)] + [number(item[attribute]) for item in records if attribute in item])
    if spec.get('legacy_key'):
        old = table.get_item(Key=spec['legacy_key'], ConsistentRead=True).get('Item', {})
        floor = max(floor, number(old.get(spec['legacy_attribute'], spec.get('start', 0))))
    raise_floor(spec['table'], floor)
    assigned = 0
    if spec.get('assign_missing'):
        for item in records:
            if attribute in item:
                continue
            value = allocate(spec['table'])
            aliases = {'#n': attribute, **{f'#k{i}': key for i, key in enumerate(spec['keys'])}}
            present = ' AND '.join(f'attribute_exists(#k{i})' for i in range(len(spec['keys'])))
            try:
                table.update_item(Key={key: item[key] for key in spec['keys']},
                    UpdateExpression='SET #n=:number',
                    ConditionExpression=present + ' AND attribute_not_exists(#n)',
                    ExpressionAttributeNames=aliases, ExpressionAttributeValues={':number': value})
                assigned += 1
            except ClientError as error:
                # A deletion or another writer winning the assignment may leave a gap.
                # The condition prevents recreating a deleted item or changing its number.
                if not conditional_failure(error):
                    raise
    counters.update_item(Key={'counter_name': spec['table']},
        UpdateExpression='SET record_count=:count, counted_at=:end, scan_started_at=:start, number_attribute=:attr',
        ExpressionAttributeValues={':count': len(records), ':end': now_iso(),
            ':start': observed_at, ':attr': attribute})
    return {'table': spec['table'], 'record_count': len(records), 'assigned': assigned}


def lambda_handler(event, context):
    results = []
    failures = []
    for spec in specs:
        try:
            results.append(reconcile_table(spec))
        except Exception as error:
            print(json.dumps({'table': spec['table'], 'error_type': type(error).__name__}))
            failures.append(spec['table'])
    if failures:
        raise RuntimeError('Counter refresh failed for: ' + ', '.join(failures))
    return {'tables': results}
