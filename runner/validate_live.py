"""Execute live reference/starter fixture checks and retain each result."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios.fixtures import SCENARIOS, materialize
from evaluator.live import evaluate

ROOT = Path(__file__).resolve().parents[2]


def main():
    results=[]
    for name in ('dbt-refunds','dbt-join','dt-region','dt-corrections'):
        for version in ('reference','starter'):
            run_id = name+'-'+version
            directory=ROOT/'runs/live-fixture-checks'/run_id
            evidence=ROOT/'results/live-fixture-checks'/run_id
            candidate=materialize(name,directory,reference=version=='reference')
            started=time.monotonic()
            error=None
            try:
                evaluate(name,candidate,'R_'+run_id.replace('-','_').upper(),evidence)
            except Exception as exception:
                error=type(exception).__name__+': '+str(exception)
            record={'scenario':name,'version':version,'passed':error is None,'expected_pass':version=='reference','error':error,'seconds':round(time.monotonic()-started,2)}
            results.append(record)
            output=ROOT/'results/live-fixture-checks.json'
            output.write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps(record),flush=True)
            if version=='reference' and error:
                raise SystemExit('Reference failed; fix harness before running further checks')

if __name__=='__main__':
    main()
