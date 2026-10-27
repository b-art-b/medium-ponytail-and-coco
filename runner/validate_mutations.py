"""Exercise live acceptance against deliberate semantic regressions."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios.fixtures import SCENARIOS, materialize
from evaluator.live import evaluate

ROOT=Path(__file__).resolve().parents[2]


def main():
    records=[]
    for name in ('dbt-refunds','dbt-join','dt-region','dt-corrections'):
        for mode in ('reference','mutation'):
            run_id=name+'-'+mode+'-v4'
            root=materialize(name,ROOT/'runs/live-validation-v4'/run_id,reference=True)
            if mode=='mutation':
                target=root/SCENARIOS[name]['target']
                text=target.read_text()
                if name=='dbt-refunds':
                    text=text.replace('sum(refund_cents)','max(refund_cents)')
                elif name=='dbt-join':
                    text=text.replace("ref('current_customers')","ref('customers')")
                elif name=='dt-region':
                    text=text.replace('FROM clean_orders GROUP BY order_day, region',"FROM clean_orders WHERE region != 'South' GROUP BY order_day, region")
                else:
                    text=text.replace('SUM(net_cents)', 'SUM(ABS(net_cents)) + 1')
                target.write_text(text)
            started=time.monotonic()
            error=None
            try:
                evaluate(name,root,'R_'+run_id.replace('-','_').upper(),ROOT/'results/live-validation-v4'/run_id)
            except Exception as exception:
                error=type(exception).__name__+': '+str(exception)
            record={'id':run_id,'passed':error is None,'expected_pass':mode=='reference','error':error,'seconds':round(time.monotonic()-started,2)}
            records.append(record)
            (ROOT/'results/live-validation-v4.json').write_text(json.dumps(records,indent=2)+'\n')
            print(json.dumps(record),flush=True)
            if (error is None)!=(mode=='reference'):
                raise SystemExit('Unexpected acceptance result')

if __name__=='__main__':
    main()
