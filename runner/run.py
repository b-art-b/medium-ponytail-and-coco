"""Automated fixed-matrix CoCo CLI benchmark; synthetic projects only."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO.parent
sys.path.insert(0,str(REPO))
from scenarios.fixtures import SCENARIOS, materialize
from evaluator.live import evaluate as evaluate_live

MODEL='claude-opus-5-5'
BLOCKED=['sql_execute','task','tool_search','direct_tool_calling','curator','web_fetch','web_search','fdbt','notebook_actions','data_diff','tgrep','skill_manage','repl_program_run','repl_program_manage','monitor','spawn_teammate','cron_create','bash_output','kill_shell']


def run_process(command, *, timeout, stdout, stderr, env=None, cwd=None):
    with open(stdout,'w') as out, open(stderr,'w') as err:
        process=subprocess.Popen(command,stdout=out,stderr=err,env=env,cwd=cwd,start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()
            return 'timeout'


def events(path):
    result=[]
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def prompt_for(name,arm):
    instruction=''
    if arm in {'B','C'}:
        instruction+='Apply the following existing coding guidance for this session, choosing the workflow appropriate to the task.\n'+(REPO/'instructions/baseline.md').read_text()+'\n'
    if arm=='C':
        instruction+='Additionally activate Ponytail full mode for this session using this exact core skill:\n'+(REPO/'instructions/ponytail.md').read_text()+'\n'
    return instruction+'''\nImplement the approved task below now; the benchmark design and task scope are already approved. Work autonomously. Do not enter plan mode or ask for approval. Read the project first. File/search tools MUST receive explicit absolute paths under the working directory, including glob and grep. Use normal bundled domain guidance when relevant. Keep all reads and edits in this project, apart from read-only bundled skill references. Do not access real accounts or external services. Do not modify TASK.md, seed data, orders.json or test_public.py. Tests may be added. Your one available test command is exactly `python -m pytest -q`; the harness executes it inside a network-disabled container with pytest/Streamlit/dbt installed. Live dbt builds and Dynamic Table execution are performed independently AFTER your session; do not pretend they ran locally. Finish with a concise account of changes, checks and limits.\n\nTASK:\n'''+SCENARIOS[name]['prompt']


def candidate_command(candidate,prompt):
    return [str(Path.home()/'.local/bin/cortex'),'--connection',os.environ.get('BENCH_COCO_CONNECTION', 'default'),'--workdir',str(candidate),
            '--setting-sources','','--config',str(REPO/'instructions/base-settings.json'),
            '--only-explicit-skills','--only-explicit-plugins','--only-explicit-profiles',
            '--plugin-dir',str(REPO/'runner/guard-plugin'),'--no-mcp','--no-auto-update','--sql-read-only',
            '--model',MODEL,'--effort','medium','--max-turns','25','--output-format','stream-json',
            '--disallowed-tools',*BLOCKED,'--allowed-tools','read','write','edit','glob','grep','bash','skill_view','skills_list',
            '--print',prompt]


def local_evaluation(name,candidate,evidence):
    code="import sys; sys.path.insert(0, '/evaluator'); from local import evaluate; evaluate(sys.argv[1], '/candidate')"
    command=['/usr/local/bin/docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
             '--security-opt','no-new-privileges','--pids-limit','128','--memory','1g','--cpus','1',
             '--tmpfs','/tmp:rw,nosuid,size=128m','--mount',f'type=bind,source={candidate},target=/candidate',
             '--mount',f'type=bind,source={REPO}/evaluator,target=/evaluator,readonly',
             '-e','PYTHONDONTWRITEBYTECODE=1','-e','HOME=/tmp','ponytail-benchmark-tests:local',
             'python','-c',code,name]
    status=run_process(command,timeout=90,stdout=evidence/'acceptance.stdout',stderr=evidence/'acceptance.stderr')
    return status==0, status


def diff_stats(name,candidate,evidence):
    old=SCENARIOS[name]['files']
    production={'added':0,'deleted':0}
    tests={'added':0,'deleted':0}
    patch=[]
    for relative in sorted(set(old)|{str(path.relative_to(candidate)) for path in candidate.rglob('*') if path.is_file() and not any(part.startswith('.') or part in {'__pycache__','target','logs','dbt_packages'} for part in path.relative_to(candidate).parts)}):
        if relative=='TASK.md':
            continue
        path=candidate/relative
        if path.exists() and path.stat().st_size>200000:
            continue
        try:
            after=path.read_text() if path.exists() else ''
        except UnicodeDecodeError:
            continue
        before=old.get(relative,'')
        delta=list(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='a/'+relative,tofile='b/'+relative))
        patch.extend(delta)
        bucket=tests if Path(relative).name.startswith('test_') or 'tests' in Path(relative).parts else production
        bucket['added']+=sum(line.startswith('+') and not line.startswith('+++') for line in delta)
        bucket['deleted']+=sum(line.startswith('-') and not line.startswith('---') for line in delta)
    (evidence/'changes.diff').write_text(''.join(patch))
    return {'production':production,'tests':tests}


def one(name,arm,repetition,phase):
    run_id=f'{name}-{arm.lower()}-{repetition}'
    evidence=ROOT/'results'/phase/run_id
    if (evidence/'result.json').exists():
        return json.loads((evidence/'result.json').read_text())
    if evidence.exists():
        raise RuntimeError(f'Incomplete attempt {run_id}; inspect rather than overwrite')
    evidence.mkdir(parents=True)
    candidate=materialize(name,ROOT/'runs'/phase/run_id)
    prompt=prompt_for(name,arm)
    (evidence/'prompt.txt').write_text(prompt)
    started=time.monotonic()
    exit_status=run_process(candidate_command(candidate,prompt),timeout=600,stdout=evidence/'agent.jsonl',stderr=evidence/'agent.stderr')
    duration=round(time.monotonic()-started,2)
    stream=events(evidence/'agent.jsonl')
    final=next((event for event in reversed(stream) if event.get('type')=='result'),{})
    record={'id':run_id,'scenario':name,'arm':arm,'repetition':repetition,'phase':phase,'model':MODEL,'agent_seconds':duration,'exit_status':exit_status,'agent_success':exit_status==0 and final.get('is_error') is False,'agent_subtype':final.get('subtype'),'usage':final.get('usage',{}),'model_usage':final.get('modelUsage',{}),'turns':final.get('num_turns'),'session_id':final.get('session_id'),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'status':'pending_evaluation'}
    record['diff']=diff_stats(name,candidate,evidence)
    (evidence/'final.txt').write_text(final.get('result',''))
    protected=[relative for relative in SCENARIOS[name]['files'] if Path(relative).name in {'test_public.py','orders.json'} or relative.startswith('seeds/')]
    record['protected_inputs_intact']=all((candidate/relative).read_text()==SCENARIOS[name]['files'][relative] for relative in protected)
    evaluated=time.monotonic()
    try:
        if not record['protected_inputs_intact']:
            record['status']='protected_input_modified'
        elif exit_status=='timeout':
            record['status']='timeout'
        elif not record['agent_success']:
            record['status']='agent_error'
            record['errors']=final.get('errors',[])
        elif SCENARIOS[name]['kind'] in {'python','streamlit'}:
            passed,status=local_evaluation(name,candidate,evidence)
            record['status']='pass' if passed else 'acceptance_fail'
            record['evaluator_exit_status']=status
        else:
            evaluate_live(name,candidate,'R_'+run_id.replace('-','_').upper(),evidence)
            record['status']='pass'
    except AssertionError as error:
        record['status']='acceptance_fail'
        record['evaluation_error']=str(error)
    except Exception as error:
        record['status']='evaluation_error'
        record['evaluation_error']=type(error).__name__+': '+str(error)
    record['evaluation_seconds']=round(time.monotonic()-evaluated,2)
    (evidence/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({key:record[key] for key in ('id','status','agent_seconds','evaluation_seconds')}),flush=True)
    return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['pilot-v2','matrix'],required=True)
    args=parser.parse_args()
    if args.phase=='pilot-v2':
        jobs=[('python-format',arm,0) for arm in 'ABC']
    else:
        pilot=[json.loads(path.read_text()) for path in (ROOT/'results/pilot-v2').glob('*/result.json')]
        if len(pilot)!=3 or any(item['status']!='pass' for item in pilot):
            raise SystemExit('Balanced pilot must pass before matrix')
        jobs=[]
        randomizer=random.Random(20261019)
        for repetition in range(1,4):
            names=list(SCENARIOS)
            randomizer.shuffle(names)
            for name in names:
                arms=list('ABC')
                randomizer.shuffle(arms)
                jobs.extend((name,arm,repetition) for arm in arms)
    started=time.monotonic()
    for job in jobs:
        if time.monotonic()-started>21600:
            print('Scheduling budget exhausted',flush=True)
            break
        record=one(*job,args.phase)
        if record['status']=='agent_error' and any('usage limit' in text.lower() or 'not enabled' in text.lower() for text in record.get('errors',[])):
            raise SystemExit('Inference unavailable; stopping matrix')

if __name__=='__main__':
    main()
