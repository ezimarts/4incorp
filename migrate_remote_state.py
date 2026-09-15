"""Create the state bucket and migrate the main and bootstrap Terraform states.

Run from a user session with AWS CLI profile 4incorp and Terraform >= 1.10.
Terraform asks for confirmation when applying the bucket plan and copying state.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ACCOUNT = '424123860784'
BUCKET = '4incorp-s3-tfstate-424123860784-us-east-1'
REGION = 'us-east-1'
KEY = '4incorp/terraform.tfstate'
BOOTSTRAP_KEY = 'bootstrap/terraform.tfstate'
RESOURCES = {
    'aws_s3_bucket.terraform_state', 'aws_s3_bucket_public_access_block.terraform_state',
    'aws_s3_bucket_versioning.terraform_state',
    'aws_s3_bucket_server_side_encryption_configuration.terraform_state',
    'aws_s3_bucket_policy.terraform_state',
}


def run(command, root, capture=False):
    completed = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=capture)
    if completed.returncode:
        # Never echo captured state or plan JSON; it may contain secrets.
        raise RuntimeError('Command failed: ' + ' '.join(command[:2]) +
                           ('\n' + completed.stderr if capture else ''))
    return completed.stdout if capture else None


def aws(root, service, operation, *arguments):
    return json.loads(run(['aws', service, operation, *arguments, '--profile', '4incorp',
        '--region', REGION, '--output', 'json', '--no-cli-pager'], root, True) or '{}')


def read_state(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not value.get('lineage') or 'serial' not in value:
        raise RuntimeError('Invalid state file: ' + str(path))
    return value


def verify_copy(before, after):
    if before.get('lineage') != after.get('lineage'):
        raise RuntimeError('State lineage mismatch. Backup retained; do not apply infrastructure changes.')
    if after.get('serial', -1) < before.get('serial', 0):
        raise RuntimeError('Remote state serial is older than the source.')
    for field in ('resources', 'outputs', 'check_results'):
        if before.get(field) != after.get(field):
            raise RuntimeError('State ' + field + ' differ. Backup retained; inspect before continuing.')


def initialized_backend(root):
    path = root / '.terraform' / 'terraform.tfstate'
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8-sig')).get('backend') or {}


def backend_text(template, key):
    return template.replace('4incorp/terraform.tfstate', key)


def assert_default_workspace(root):
    env = root / '.terraform' / 'environment'
    if env.exists() and env.read_text().strip() != 'default':
        raise RuntimeError('This helper only migrates the default workspace. Other workspaces need a separate reviewed migration.')
    directory = root / 'terraform.tfstate.d'
    if directory.exists() and any(directory.rglob('terraform.tfstate')):
        raise RuntimeError('Additional local workspace states found; stop and include them in the migration plan.')


def migrate(root, template, key, backup_directory):
    assert_default_workspace(root)
    config = root / 'backend.tf'
    expected = backend_text(template, key)
    if config.exists() and config.read_text(encoding='utf-8-sig').strip() != expected.strip():
        raise RuntimeError('An unexpected backend.tf already exists in ' + str(root))
    active = initialized_backend(root)
    if active.get('type') not in (None, 'local', 's3'):
        raise RuntimeError('Unexpected existing backend in ' + str(root))
    if active.get('type') == 's3':
        actual = active.get('config', {})
        if actual.get('bucket') != BUCKET or actual.get('key') != key:
            raise RuntimeError('A different S3 backend is already configured; refusing to migrate it.')
        state = json.loads(run(['terraform', 'state', 'pull'], root, True))
        manifest = backup_directory / (root.name + '-source.tfstate')
        if manifest.exists():
            verify_copy(read_state(manifest), state)
        print('Already using verified S3 backend: ' + key)
        return
    local = root / 'terraform.tfstate'
    if not local.exists():
        raise RuntimeError('Local state file missing: ' + str(local))
    source = read_state(local)
    if not source.get('resources'):
        raise RuntimeError('Local state has no resources; refusing an empty migration.')
    try:
        existing = aws(root, 's3api', 'head-object', '--bucket', BUCKET, '--key', key,
                       '--expected-bucket-owner', ACCOUNT)
    except RuntimeError as error:
        if not any(code in str(error) for code in ('(404)', '(NoSuchKey)', '(NotFound)')):
            raise
    else:
        # Recover a previous interrupted init only if the remote snapshot matches.
        remote_file = backup_directory / (root.name + '-existing-remote.tfstate')
        aws(root, 's3api', 'get-object', '--bucket', BUCKET, '--key', key,
            '--expected-bucket-owner', ACCOUNT, '--if-match', existing['ETag'], str(remote_file))
        destination_state = read_state(remote_file)
        verify_copy(source, destination_state)
        if destination_state['serial'] != source['serial']:
            raise RuntimeError('Destination has a different state serial; refusing to overwrite it.')
        print('Destination already holds the matching snapshot; continuing backend initialization.')
    backup = backup_directory / (root.name + '-source.tfstate')
    if backup.exists():
        verify_copy(read_state(backup), source)
    else:
        shutil.copy2(local, backup)
    original_digest = hashlib.sha256(local.read_bytes()).hexdigest()
    # Backend configuration is added only after the bucket has been created.
    config.write_text(expected, encoding='utf-8')
    if hashlib.sha256(local.read_bytes()).hexdigest() != original_digest:
        raise RuntimeError('Local state changed while preparing migration. Stop all other Terraform processes.')
    print('Terraform will ask to copy existing state. Answer yes to migrate ' + key)
    run(['terraform', 'init', '-migrate-state'], root)
    actual = initialized_backend(root)
    if actual.get('type') != 's3' or actual.get('config', {}).get('key') != key or actual.get('config', {}).get('bucket') != BUCKET:
        raise RuntimeError('S3 backend initialization was not verified.')
    remote = json.loads(run(['terraform', 'state', 'pull'], root, True))
    verify_copy(source, remote)
    print('Verified remote state: ' + key + ' (resource values, outputs, lineage and serial checked)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(r'C:\Users\Zahid Ullah\ezm\projects\4incorp'))
    args = parser.parse_args()
    root = args.project.resolve()
    bootstrap = root / 'terraform-state-bootstrap'
    template_path = root / 'backend.tf.template'
    if not bootstrap.joinpath('main.tf').exists() or not template_path.exists():
        raise RuntimeError('Install the bootstrap configuration and backend template first.')
    # Respect the project's standard .terraform data folder; custom overrides require review.
    import os
    if os.environ.get('TF_DATA_DIR') or os.environ.get('TF_WORKSPACE', 'default') != 'default':
        raise RuntimeError('Unset TF_DATA_DIR/TF_WORKSPACE overrides before using this default-workspace helper.')
    if any(value for key, value in os.environ.items() if key.startswith('TF_CLI_ARGS')):
        raise RuntimeError('Remove TF_CLI_ARGS overrides from this shell before running the migration helper.')
    assert_default_workspace(root)
    for file in root.glob('*.tf'):
        if file.name != 'backend.tf' and re.search(r'\b(?:backend\s+"|cloud\s*\{)', file.read_text(encoding='utf-8-sig')):
            raise RuntimeError('An existing backend/cloud block needs review: ' + file.name)
    version = json.loads(run(['terraform', 'version', '-json'], root, True))['terraform_version']
    if tuple(map(int, version.split('-')[0].split('.')[:2])) < (1, 10):
        raise RuntimeError('Terraform >= 1.10 is required for S3-native locking.')
    if aws(root, 'sts', 'get-caller-identity').get('Account') != ACCOUNT:
        raise RuntimeError('Wrong AWS account; expected ' + ACCOUNT)
    record = root / '.tmp' / 'remote-state-migration.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    if record.exists():
        backup = Path(json.loads(record.read_text())['backup_directory'])
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = root / 'state-backups' / ('remote-state-' + stamp)
        backup.mkdir(parents=True, exist_ok=False)
        record.write_text(json.dumps({'backup_directory': str(backup)}, indent=2), encoding='utf-8')
    # Save the main local state before any AWS creation or Terraform initialization.
    main_local = root / 'terraform.tfstate'
    early_backup = backup / (root.name + '-source.tfstate')
    if main_local.exists() and not early_backup.exists():
        read_state(main_local)
        shutil.copy2(main_local, early_backup)
    print('State backups: ' + str(backup))
    template = template_path.read_text(encoding='utf-8-sig')
    if bootstrap.joinpath('backend.tf').exists() and initialized_backend(bootstrap).get('type') != 's3':
        migrate(bootstrap, template, BOOTSTRAP_KEY, backup)
    run(['terraform', 'init'], bootstrap)
    plan = backup / 'state-bucket.tfplan'
    run(['terraform', 'plan', '-out=' + str(plan)], bootstrap)
    planned = json.loads(run(['terraform', 'show', '-json', str(plan)], bootstrap, True))
    for change in planned.get('resource_changes', []):
        actions = change['change']['actions']
        if change.get('mode') == 'data' or actions == ['no-op']:
            continue
        if change['address'] not in RESOURCES or 'delete' in actions:
            raise RuntimeError('Unexpected bootstrap change or deletion: ' + change['address'])
    print('This plan only manages the dedicated state bucket and its protections.')
    if input('Type APPLY to create/configure the state bucket: ').strip() != 'APPLY':
        raise RuntimeError('Stopped before applying the bucket plan.')
    run(['terraform', 'apply', str(plan)], bootstrap)
    aws(root, 's3api', 'head-bucket', '--bucket', BUCKET, '--expected-bucket-owner', ACCOUNT)
    versioning = aws(root, 's3api', 'get-bucket-versioning', '--bucket', BUCKET, '--expected-bucket-owner', ACCOUNT)
    if versioning.get('Status') != 'Enabled':
        raise RuntimeError('Bucket versioning is not enabled; refusing state migration.')
    migrate(root, template, KEY, backup)
    migrate(bootstrap, template, BOOTSTRAP_KEY, backup)
    print('Complete. Both Terraform states now use S3 locking and versioned remote storage.')
    print('Do not use old saved plans. Run a fresh terraform plan in the main project next.')


if __name__ == '__main__':
    main()
