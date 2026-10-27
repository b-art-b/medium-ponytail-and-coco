"""Read-only aggregate from immutable per-run result records."""
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[2]


def summarize(records):
    summaries={}
    median_turns=lambda rows: round(median(row['turns'] for row in rows),2) if rows else None
    for arm in 'ABC':
        group=[row for row in records if row['arm']==arm]
        successful=[row for row in group if row['status']=='pass']
        def med(rows, field):
            return round(median(field(row) for row in rows),2) if rows else None
        summaries[arm]={
            'completed':len(group),'passed':len(successful),
            'median_agent_seconds_all':med(group,lambda row:row['agent_seconds']),
            'median_agent_seconds_passed':med(successful,lambda row:row['agent_seconds']),
            'median_production_added_passed':med(successful,lambda row:row['diff']['production']['added']),
            'median_production_churn_passed':med(successful,lambda row:sum(row['diff']['production'].values())),
            'median_test_added_passed':med(successful,lambda row:row['diff']['tests']['added']),
            'median_turns_passed':median_turns(successful),
            'median_output_tokens_all':med(group,lambda row:row['usage'].get('output_tokens',0)),
            'total_input_tokens':sum(row['usage'].get('input_tokens',0) for row in group),
            'total_cache_creation_tokens':sum(row['usage'].get('cache_creation_input_tokens',0) for row in group),
            'total_cache_read_tokens':sum(row['usage'].get('cache_read_input_tokens',0) for row in group),
            'total_output_tokens':sum(row['usage'].get('output_tokens',0) for row in group),
        }
    indexed={(row['scenario'],row['repetition'],row['arm']):row for row in records}
    pairs=[]
    for scenario, repetition in sorted({(row['scenario'],row['repetition']) for row in records}):
        baseline=indexed.get((scenario,repetition,'B'))
        ponytail=indexed.get((scenario,repetition,'C'))
        if baseline and ponytail and baseline['status']==ponytail['status']=='pass':
            pairs.append({'scenario':scenario,'repetition':repetition,
                          'time_delta_seconds':round(ponytail['agent_seconds']-baseline['agent_seconds'],2),
                          'production_added_delta':ponytail['diff']['production']['added']-baseline['diff']['production']['added'],
                          'output_tokens_delta':ponytail['usage'].get('output_tokens',0)-baseline['usage'].get('output_tokens',0)})
    return {'runs':len(records),'expected_runs':72,'arms':summaries,'matched_successful_B_C':pairs,
            'scenarios':{name:{arm:{'passed':sum(row['status']=='pass' for row in records if row['scenario']==name and row['arm']==arm),'completed':sum(row['scenario']==name and row['arm']==arm for row in records)} for arm in 'ABC'} for name in sorted({row['scenario'] for row in records})},
            'failures':[{key:row.get(key) for key in ('id','status','evaluation_error','errors')} for row in records if row['status']!='pass']}


def main():
    records=[json.loads(path.read_text()) for path in sorted((ROOT/'results/matrix').glob('*/result.json'))]
    result=summarize(records)
    # Secondary scoring: dbt hidden-data step rebuilds models only (runner/rescore_dbt.py).
    rescore={row['id']:row['models_only_status'] for row in json.loads((ROOT/'results/dbt-rescore.json').read_text())}
    result['models_only_dbt']=summarize([{**row,'status':rescore.get(row['id'],row['status'])} for row in records])
    (ROOT/'results/summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'results/all-runs.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
