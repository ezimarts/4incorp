"""Deploy central counters, then switch allocation during a brief API pause.

Uses Terraform and AWS CLI from the user's own session. Python stdlib only.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

ACCOUNT = '424123860784'
ALLOWED_CHANGES = {
    'aws_lambda_function.fourincorp_api',
    'aws_iam_role_policy.central_counter_api',
    'aws_iam_role.counter_sync',
    'aws_iam_role_policy_attachment.counter_sync_logs',
    'aws_iam_role_policy.counter_sync',
    'aws_lambda_function.counter_sync',
    'aws_cloudwatch_event_rule.counter_sync',
    'aws_cloudwatch_event_target.counter_sync',
    'aws_lambda_permission.counter_sync_schedule',
    'aws_cloudwatch_metric_alarm.counter_sync_errors',
}


def run(command, cwd, capture=False):
    result = subprocess.run(command, cwd=cwd, text=True, encoding='utf-8',
                            capture_output=capture)
    if result.returncode:
        raise RuntimeError('Command failed: ' + command[0] + ' ' + command[1] +
                           ('\n' + result.stderr if capture else ''))
    return result.stdout if capture else None


def aws(args, service, operation, extra=()):
    return json.loads(run(['aws', service, operation, *extra, '--profile', args.profile,
        '--region', 'us-east-1', '--output', 'json', '--no-cli-pager'], args.project, True) or '{}')


def settings(path, enabled, paused):
    values = {'fourincorp_central_counters_enabled': enabled,
              'fourincorp_counter_cutover_pause': paused}
    path.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')


def deploy(args, stage):
    plan = str(args.work / (stage + '.tfplan'))
    run(['terraform', 'plan', '-out=' + plan], args.project)
    data = json.loads(run(['terraform', 'show', '-json', plan], args.project, True))
    for resource in data.get('resource_changes', []):
        actions = resource['change']['actions']
        if resource['address'] == 'aws_lambda_function.fourincorp_api':
            before = (resource['change'].get('before') or {}).get('environment', [])
            after = (resource['change'].get('after') or {}).get('environment', [])
            old_flag = (before[0].get('variables', {}) if before else {}).get('CENTRAL_COUNTERS_ENABLED')
            new_flag = (after[0].get('variables', {}) if after else {}).get('CENTRAL_COUNTERS_ENABLED')
            if old_flag == 'true' and new_flag != 'true':
                raise RuntimeError('Refusing to revert active central sequences to stale legacy counters.')
        if resource.get('mode') == 'data' or actions == ['no-op']:
            continue
        if resource['address'] not in ALLOWED_CHANGES or 'delete' in actions:
            raise RuntimeError('Plan includes an unrelated change or deletion: ' + resource['address'] +
                '. Review and resolve it separately before retrying. Nothing from this plan was applied.')
    run(['terraform', 'apply', plan], args.project)


def tf_output(args, name):
    return run(['terraform', 'output', '-raw', name], args.project, True).strip()


def refresh(args):
    function = tf_output(args, 'central_counter_sync_function')
    output = args.work / 'counter-refresh.json'
    for attempt in range(12):
        try:
            result = aws(args, 'lambda', 'invoke', ['--function-name', function,
                '--cli-read-timeout', '300', '--cli-binary-format', 'raw-in-base64-out',
                '--payload', '{}', str(output)])
            break
        except RuntimeError as error:
            if 'TooManyRequestsException' not in str(error) or attempt == 11:
                raise
            time.sleep(30)
    if result.get('FunctionError'):
        raise RuntimeError('Counter refresh failed; inspect ' + str(output) + '. API remains paused if cutover started.')
    report = json.loads(output.read_text(encoding='utf-8'))
    if len(report.get('tables', [])) != 8:
        raise RuntimeError('Expected successful refresh of all eight tables. Inspect ' + str(output))


def runtime_is_central(args):
    function = tf_output(args, 'central_counter_api_function')
    # Query only the feature flag, never display other environment values.
    result = aws(args, 'lambda', 'get-function-configuration', ['--function-name', function,
        '--query', 'Environment.Variables.CENTRAL_COUNTERS_ENABLED'])
    return result == 'true'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['setup', 'cutover', 'resume', 'refresh'])
    parser.add_argument('--project', type=Path, default=Path(r'C:\Users\Zahid Ullah\ezm\projects\4incorp'))
    parser.add_argument('--profile', default='4incorp')
    args = parser.parse_args()
    args.work = args.project / '.tmp' / 'central-counters'
    args.work.mkdir(parents=True, exist_ok=True)
    config = args.project / 'central-counters.auto.tfvars.json'
    if aws(args, 'sts', 'get-caller-identity').get('Account') != ACCOUNT:
        raise RuntimeError('Wrong AWS account. Expected ' + ACCOUNT)
    if not (args.project / 'central-counters.tf').exists():
        raise RuntimeError('Install the prepared project files before deployment.')
    if args.stage == 'setup':
        if config.exists():
            previous = json.loads(config.read_text())
            if previous.get('fourincorp_central_counters_enabled') or previous.get('fourincorp_counter_cutover_pause'):
                raise RuntimeError('A cutover is already active or paused. Use cutover/resume, not setup.')
        settings(config, False, False)
        deploy(args, 'counter-setup')
        refresh(args)
        print('Counter rows initialized. Run cutover during a short API maintenance window.')
    elif args.stage == 'refresh':
        refresh(args)
        print('Refreshed all eight counter rows.')
    elif args.stage == 'resume':
        if not runtime_is_central(args):
            raise RuntimeError('Central allocation is not active. Rerun cutover instead of resuming writes.')
        settings(config, True, False)
        deploy(args, 'counter-resume')
        print('API resumed with central allocation enabled.')
    else:
        if not config.exists():
            raise RuntimeError('Run setup before cutover.')
        active = runtime_is_central(args)
        settings(config, active, True)
        deploy(args, 'counter-pause')
        print('API is paused. Waiting 35 seconds for in-flight requests to finish.')
        time.sleep(35)
        refresh(args)
        if not active:
            settings(config, True, True)
            deploy(args, 'counter-activate')
        if not runtime_is_central(args):
            raise RuntimeError('Allocation switch was not verified; API remains paused.')
        settings(config, True, False)
        deploy(args, 'counter-resume')
        print('Completed: client/order numbers now allocate from the central counters table. API resumed.')


if __name__ == '__main__':
    main()
