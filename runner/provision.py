"""Provision approved disposable benchmark namespace, with a role-restricted token.

Only trusted controller runs this. Token output never goes to logs or chat.
No policy changes or network-policy bypasses are attempted.
"""
import json
import os
from pathlib import Path
import secrets
import sys

from snow import assert_account, query

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'research' / 'database-state.json'
CREDENTIAL = ROOT / 'research' / '.benchmark-token'


def main():
    assert_account()
    if STATE.exists():
        raise SystemExit('State already exists; inspect before provisioning again')
    suffix = secrets.token_hex(4).upper()
    database = 'PONYTAIL_BENCH_' + suffix
    role = database + '_ROLE'
    token = database + '_TOKEN'
    state = {'database': database, 'role': role, 'token_name': token, 'created': [], 'status': 'provisioning'}
    def save():
        STATE.write_text(json.dumps(state, indent=2) + '\n')
    save()
    for kind, sql in [
        ('database', f'CREATE TRANSIENT DATABASE {database} DATA_RETENTION_TIME_IN_DAYS=0'),
        ('role', f'CREATE ROLE {role}'),
        ('warehouse_grant', f'GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE {role}'),
        ('database_grant', f'GRANT USAGE, CREATE SCHEMA ON DATABASE {database} TO ROLE {role}'),
        ('user_grant', f'GRANT ROLE {role} TO USER BART'),
    ]:
        query(sql)
        state['created'].append(kind)
        save()
    try:
        result = query(f"ALTER USER BART ADD PROGRAMMATIC ACCESS TOKEN {token} ROLE_RESTRICTION='{role}' DAYS_TO_EXPIRY=1 COMMENT='Disposable Ponytail benchmark evaluator'")
        token_row = {key.lower(): value for key, value in result[0].items()}
        secret = token_row['token_secret']
        with os.fdopen(os.open(CREDENTIAL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
            handle.write(secret)
        state['created'].append('token')
        state['status'] = 'provisioned-not-verified'
        save()
    except Exception:
        state['status'] = 'token-provision-failed'
        save()
        raise RuntimeError('Restricted credential could not be provisioned; no candidate SQL executed') from None
    print(json.dumps({key: value for key, value in state.items() if key != 'token_name'}, indent=2))

if __name__ == '__main__':
    main()
