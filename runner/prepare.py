"""Freeze scenario metadata and author-approved instruction snapshots locally."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
from scenarios.fixtures import SCENARIOS, materialize


def main():
    instructions=REPO/'instructions'
    sources=[Path.home()/'.snowflake/cortex/AGENTS.md', *[Path.home()/f'.snowflake/cortex/skills/{name}/SKILL.md' for name in ('lean-build','surgical-patch','verify-and-stop')]]
    content=[]
    hashes={}
    for path in sources:
        text=path.read_text()
        hashes[path.name if path.name=='AGENTS.md' else path.parent.name]=hashlib.sha256(text.encode()).hexdigest()
        content.append(text)
    baseline='\n\n'.join(content)
    (instructions/'baseline.md').write_text(baseline)
    ponytail=(REPO/'third_party/ponytail/skills/ponytail/SKILL.md').read_text()
    (instructions/'ponytail.md').write_text(ponytail)
    (instructions/'arms.json').write_text(json.dumps({'A':{'instructions':[]},'B':{'instructions':['baseline.md']},'C':{'instructions':['baseline.md','ponytail.md']},'delivery':'Explicit instruction snapshot in session prompt; not global plugin activation','baseline_source_hashes':hashes,'ponytail_commit':'09c434ab73ca43761c5d8b0c5d341926c2fba710'},indent=2)+'\n')
    manifest={}
    for name, item in SCENARIOS.items():
        fixture=REPO/'scenarios'/name
        if not fixture.exists():
            materialize(name,fixture)
        manifest[name]={'kind':item['kind'],'prompt':item['prompt'],'fixture_files':{file:hashlib.sha256(text.encode()).hexdigest() for file,text in item['files'].items()}}
    (REPO/'scenarios/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    plan=ROOT.parent/'.snowflake/cortex/plans/ponytail-coco-benchmark.plan.md'
    shutil.copyfile(plan,ROOT/'plan.md')
    print('Exported eight starter fixtures and instruction snapshots; not frozen until pilot passes.')

if __name__=='__main__':
    main()
