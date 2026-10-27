"""Live fixture evaluation. CLI SQL and dbt both use the benchmark-only user."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / 'git'


def state():
    value = json.loads((ROOT/'research/database-state.json').read_text())
    if value['status'] != 'restricted-service-auth-verified':
        raise RuntimeError('Restricted evaluator identity is not verified')
    return value


def sql(text, schema=None):
    settings = state()
    command = [str(Path.home()/'.local/bin/snow'), 'sql', '-x', '--account', os.environ['BENCH_ACCOUNT'],
               '--user', settings['service_user'], '--authenticator', 'SNOWFLAKE_JWT',
               '--private-key-file', str(ROOT/'research/.benchmark-key.p8'),
               '--role', settings['role'], '--secondary-roles', 'NONE', '--warehouse', 'COMPUTE_WH',
               '--database', settings['database'], '--silent', '--format', 'JSON', '--stdin', '--local-only']
    if schema:
        if not re.fullmatch(r'R_[A-Z0-9_]+', schema):
            raise ValueError('Invalid run schema')
        command += ['--schema', schema]
    run = subprocess.run(command, input=text, capture_output=True, text=True, timeout=120)
    if run.returncode:
        raise RuntimeError(run.stderr[:2500])
    return json.loads(run.stdout)


RAW = '''CREATE TABLE raw_orders(order_id STRING, order_day DATE, region STRING, gross_cents NUMBER(18,0), refund_cents NUMBER(18,0)) CHANGE_TRACKING=TRUE;
INSERT INTO raw_orders VALUES ('a','2026-01-01','North',1000,200),('b','2026-01-01','South',500,500),('c','2026-01-02','North',2000,NULL);
'''


def rows(query, schema):
    return sql(query, schema)


def check_dynamic(name, root, schema):
    sql(RAW, schema)
    ddl = (root/'pipeline.sql').read_text()
    # Supplemental validation only. Restricted service identity is the privilege boundary.
    import sqlparse
    statements = sqlparse.split(ddl)
    for statement in statements:
        stripped = sqlparse.format(statement, strip_comments=True).strip()
        if not re.match(r'CREATE\s+(?:OR\s+ALTER\s+)?DYNAMIC\s+TABLE\s+(clean_orders|daily_sales|regional_sales)\b', stripped, re.I):
            raise ValueError('Fixture permits only its three Dynamic Table definitions')
    sql(ddl, schema)
    sql('ALTER DYNAMIC TABLE daily_sales REFRESH', schema)
    assert rows('SELECT order_day::varchar AS DAY, net_cents AS NET FROM daily_sales ORDER BY DAY', schema) == [
        {'DAY': '2026-01-01', 'NET': 800}, {'DAY': '2026-01-02', 'NET': 2000}]
    if name == 'dt-region':
        sql('ALTER DYNAMIC TABLE regional_sales REFRESH', schema)
        assert rows('SELECT order_day::varchar AS DAY, region AS REGION, net_cents AS NET FROM regional_sales ORDER BY DAY, REGION', schema) == [
            {'DAY':'2026-01-01','REGION':'North','NET':800}, {'DAY':'2026-01-01','REGION':'South','NET':0}, {'DAY':'2026-01-02','REGION':'North','NET':2000}]
    sql("UPDATE raw_orders SET refund_cents=300, region='West' WHERE order_id='a'; DELETE FROM raw_orders WHERE order_id='b'; INSERT INTO raw_orders VALUES ('d','2026-01-02','South',900,100)", schema)
    sql('ALTER DYNAMIC TABLE daily_sales REFRESH', schema)
    assert rows('SELECT order_day::varchar AS DAY, net_cents AS NET FROM daily_sales ORDER BY DAY', schema) == [
        {'DAY':'2026-01-01','NET':700}, {'DAY':'2026-01-02','NET':2800}]
    if name == 'dt-region':
        sql('ALTER DYNAMIC TABLE regional_sales REFRESH', schema)
        assert rows('SELECT order_day::varchar AS DAY, region AS REGION, net_cents AS NET FROM regional_sales ORDER BY DAY, REGION', schema) == [
            {'DAY':'2026-01-01','REGION':'West','NET':700}, {'DAY':'2026-01-02','REGION':'North','NET':2000}, {'DAY':'2026-01-02','REGION':'South','NET':800}]
    sql('DELETE FROM raw_orders', schema)
    sql('ALTER DYNAMIC TABLE daily_sales REFRESH', schema)
    assert rows('SELECT * FROM daily_sales', schema) == []


def check_dbt(name, root, schema, evidence, hidden='build'):
    settings = state()
    profiles = evidence/'profiles'
    profiles.mkdir()
    # No secret values: private key stays outside the candidate project.
    import yaml
    profile = {'retail_benchmark': {'target':'test','outputs':{'test':{
        'type':'snowflake','account':os.environ['BENCH_ACCOUNT'],'user':settings['service_user'],
        'private_key_path':'/credentials/key.p8','role':settings['role'],
        'database':settings['database'],'schema':schema,'warehouse':'COMPUTE_WH','threads':1,
        'client_session_keep_alive':False,'session_parameters':{'STATEMENT_TIMEOUT_IN_SECONDS':90}}}}}
    (profiles/'profiles.yml').write_text(yaml.safe_dump(profile))
    # hidden='run' rebuilds models only on fresh data, so candidate-authored tests pinned to seed values are not rerun.
    for command, variant in (('seed', False), ('build', False), (hidden, True)):
        if variant:
            sql("INSERT INTO orders VALUES ('d','c3','2026-01-03',700),('e','c1','2026-01-03',200),('f','unknown','2026-01-03',300); INSERT INTO refunds VALUES ('r4','d',100),('r5','d',100),('r6','e',NULL); INSERT INTO customers VALUES ('c3',1,'Old'),('c3',3,'West'),('c1',3,'East')", schema)
        invocation = ['/usr/local/bin/docker', 'run', '--rm', '--read-only', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges', '--pids-limit', '128', '--memory', '1g',
                      '--tmpfs', '/tmp:rw,nosuid,size=256m',
                      '--mount', f'type=bind,source={root},target=/candidate',
                      '--mount', f'type=bind,source={profiles},target=/profiles,readonly',
                      '--mount', f'type=bind,source={ROOT}/research/.benchmark-key.p8,target=/credentials/key.p8,readonly',
                      '-e', 'HOME=/tmp', '-e', 'DBT_SEND_ANONYMOUS_USAGE_STATS=false',
                      'ponytail-benchmark-tests:local', 'dbt', command,
                      '--project-dir', '/candidate', '--profiles-dir', '/profiles', '--no-use-colors',
                      *(['--exclude-resource-type', 'seed'] if variant and command == 'build' else [])]
        result = subprocess.run(invocation,capture_output=True,text=True,timeout=180,env={**os.environ,'DBT_SEND_ANONYMOUS_USAGE_STATS':'false'})
        (evidence/f"dbt-{command}{'-variant' if variant else ''}.txt").write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(f'dbt {command} failed; see evidence')
    if name == 'dbt-refunds':
        assert rows('SELECT order_day::varchar AS DAY, net_cents AS NET FROM daily_revenue ORDER BY DAY', schema) == [
            {'DAY':'2026-01-01','NET':800},{'DAY':'2026-01-02','NET':2000},{'DAY':'2026-01-03','NET':1000}]
    else:
        assert rows('SELECT region AS REGION, gross_cents AS GROSS FROM regional_revenue ORDER BY REGION',schema) == [
            {'REGION':'East','GROSS':3200},{'REGION':'South','GROSS':500},{'REGION':'West','GROSS':700}]


def evaluate(name, root, schema, evidence, hidden='build'):
    settings = state()
    if not re.fullmatch(r'R_[A-Z0-9_]+', schema):
        raise ValueError('Invalid schema')
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        sql(f"CREATE SCHEMA {settings['database']}.{schema}")
        created = True
        if name.startswith('dt-'):
            check_dynamic(name, Path(root), schema)
        else:
            check_dbt(name, Path(root), schema, evidence, hidden)
    finally:
        if created:
            sql(f"DROP SCHEMA {settings['database']}.{schema} CASCADE")
