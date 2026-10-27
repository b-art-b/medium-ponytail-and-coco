"""Trusted SQL CLI boundary. Never expose this module to candidate agents."""
import json
import os
import subprocess
from pathlib import Path

SNOW = str(Path.home() / ".local/bin/snow")
# Test account guard, e.g. BENCH_ACCOUNT=ORG-ACCOUNT, BENCH_ACCOUNT_LOCATOR=AB12345
EXPECTED = (*os.environ['BENCH_ACCOUNT'].split('-', 1), os.environ['BENCH_ACCOUNT_LOCATOR'])
CONNECTION = os.environ.get('BENCH_SNOW_CONNECTION', 'blog')


def query(sql, *, role=None, timeout=120):
    command = [SNOW, 'sql', '-c', CONNECTION, '--format', 'JSON', '--silent', '--local-only', '--stdin']
    if role:
        command += ['--role', role, '--secondary-roles', 'NONE']
    result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[:2000])
    return json.loads(result.stdout)


def assert_account():
    row = query('SELECT CURRENT_ORGANIZATION_NAME() AS ORG, CURRENT_ACCOUNT_NAME() AS NAME, CURRENT_ACCOUNT() AS LOCATOR')[0]
    if tuple(row[key] for key in ('ORG', 'NAME', 'LOCATOR')) != EXPECTED:
        raise RuntimeError('Refusing SQL: unexpected account')
    return row


if __name__ == '__main__':
    print(json.dumps(assert_account()))
