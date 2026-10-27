"""Post-hoc dbt rescore: hidden fresh-data step rebuilds models only (dbt run), so candidate tests pinned to seed answers are not rerun."""
import json, shutil, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'git'))
from evaluator.live import evaluate

records = []
for result_file in sorted((ROOT/'results/matrix').glob('dbt-*/result.json')):
    original = json.loads(result_file.read_text())
    run_id = original['id']
    root = ROOT/'runs/dbt-rescore'/run_id
    if not root.exists():
        shutil.copytree(ROOT/'runs/matrix'/run_id, root, ignore=shutil.ignore_patterns('target', 'logs'))
    record = {'id': run_id, 'arm': original['arm'], 'scenario': original['scenario'], 'strict_status': original['status']}
    try:
        evaluate(original['scenario'], root, 'R_RS_'+run_id.replace('-', '_').upper(), ROOT/'results/dbt-rescore'/run_id, hidden='run')
        record['models_only_status'] = 'pass'
    except AssertionError:
        record['models_only_status'] = 'acceptance_fail'
    except Exception as error:
        record['models_only_status'] = 'evaluation_error'
        record['error'] = ''.join(traceback.format_exception_only(error)).strip()
    print(json.dumps(record), flush=True)
    records.append(record)
(ROOT/'results/dbt-rescore.json').write_text(json.dumps(records, indent=2)+'\n')
