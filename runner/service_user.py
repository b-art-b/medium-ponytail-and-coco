"""Provision explicitly approved temporary key-pair service identity."""
import json
import os
from pathlib import Path
import subprocess
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from snow import assert_account, query

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'research/database-state.json'


def main():
    assert_account()
    state = json.loads(STATE.read_text())
    if 'service_user' in state:
        raise SystemExit('Service identity already recorded; inspect state')
    username = state['database'] + '_USER'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = ROOT / 'research/.benchmark-key.p8'
    with os.fdopen(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
        handle.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    import base64
    encoded = base64.b64encode(public).decode()
    query(f"CREATE USER {username} TYPE=SERVICE RSA_PUBLIC_KEY='{encoded}' DEFAULT_ROLE={state['role']} DEFAULT_WAREHOUSE=COMPUTE_WH COMMENT='Disposable Ponytail benchmark evaluator'")
    state['service_user'] = username
    state['created'].append('service_user')
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    query(f"GRANT ROLE {state['role']} TO USER {username}")
    prefix = [str(Path.home()/'.local/bin/snow'), 'sql', '-x', '--account', os.environ['BENCH_ACCOUNT'],
              '--user', username, '--authenticator', 'SNOWFLAKE_JWT', '--private-key-file', str(key_path),
              '--role', state['role'], '--secondary-roles', 'NONE', '--warehouse', 'COMPUTE_WH',
              '--database', state['database'], '--silent', '--format', 'JSON', '--stdin', '--local-only']
    probe = subprocess.run(prefix, input='SELECT CURRENT_ORGANIZATION_NAME() AS ORG, CURRENT_ACCOUNT_NAME() AS ACCOUNT, CURRENT_USER() AS USERNAME, CURRENT_ROLE() AS ROLE', capture_output=True, text=True, timeout=90)
    if probe.returncode:
        raise RuntimeError(probe.stderr[:1500])
    identity = json.loads(probe.stdout)[0]
    assert (identity['ORG'], identity['ACCOUNT'], identity['USERNAME'], identity['ROLE']) == (*os.environ['BENCH_ACCOUNT'].split('-', 1), username, state['role'])
    denied = subprocess.run(prefix, input='USE ROLE ACCOUNTADMIN', capture_output=True, text=True, timeout=90)
    assert denied.returncode != 0, 'Administrator escalation succeeded'
    query(f"ALTER USER BART REMOVE PROGRAMMATIC ACCESS TOKEN {state['token_name']}")
    state['created'].remove('token')
    for path in [ROOT/'research/.benchmark-token', ROOT/'research/.restricted-snow.toml']:
        path.unlink(missing_ok=True)
    state['status'] = 'restricted-service-auth-verified'
    state['accountadmin_switch_denied'] = True
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps({'identity': identity, 'accountadmin_switch_denied': True, 'unused_token_removed': True}))

if __name__ == '__main__':
    main()
