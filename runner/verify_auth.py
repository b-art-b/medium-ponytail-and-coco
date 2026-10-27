"""Generate local restricted CLI config, then verify account and role lock."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'research/database-state.json'
CONFIG = ROOT / 'research/.restricted-snow.toml'


def main():
    state = json.loads(STATE.read_text())
    secret = (ROOT / 'research/.benchmark-token').read_text()
    config = '\n'.join([
        '[connections.benchmark]', 'account = ' + json.dumps(os.environ['BENCH_ACCOUNT']), 'user = ' + json.dumps(os.environ['BENCH_USER']),
        'authenticator = "PROGRAMMATIC_ACCESS_TOKEN"', 'token = ' + json.dumps(secret),
        'role = ' + json.dumps(state['role']), 'warehouse = "COMPUTE_WH"',
        'database = ' + json.dumps(state['database']), '',
    ])
    prefix = [str(Path.home()/'.local/bin/snow'), 'sql', '-x',
              '--account', os.environ['BENCH_ACCOUNT'], '--user', os.environ['BENCH_USER'],
              '--authenticator', 'PROGRAMMATIC_ACCESS_TOKEN',
              '--token-file-path', str(ROOT / 'research/.benchmark-token'),
              '--role', state['role'], '--warehouse', 'COMPUTE_WH',
              '--database', state['database'],
              '--silent', '--format', 'JSON', '--stdin', '--local-only']
    probe = subprocess.run(prefix, input='SELECT CURRENT_ORGANIZATION_NAME() AS ORG, CURRENT_ACCOUNT_NAME() AS ACCOUNT, CURRENT_ROLE() AS ROLE', capture_output=True, text=True, timeout=90)
    if probe.returncode:
        print(probe.stderr[:1500])
        raise SystemExit('Restricted authentication failed; no fallback')
    rows = json.loads(probe.stdout)
    assert (rows[0]['ORG'], rows[0]['ACCOUNT'], rows[0]['ROLE']) == (*os.environ['BENCH_ACCOUNT'].split('-', 1), state['role'])
    denied = subprocess.run(prefix, input='USE ROLE ACCOUNTADMIN', capture_output=True, text=True, timeout=90)
    if denied.returncode == 0:
        raise SystemExit('Privilege escalation unexpectedly succeeded; refuse evaluation')
    state['status'] = 'restricted-auth-verified'
    state['accountadmin_switch_denied'] = True
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps({'identity': rows, 'accountadmin_switch_denied': True}))

if __name__ == '__main__':
    main()
