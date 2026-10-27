import importlib.util
from pathlib import Path
import sys

import pytest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
spec=importlib.util.spec_from_file_location('guard',REPO/'runner/guard-plugin/guard.py')
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
from runner.run import events, prompt_for


def event(root, name, args):
    return {'cwd':str(root),'tool_name':name,'tool_input':args}


def test_guard_reads_project(tmp_path):
    assert guard.decide(event(tmp_path,'read',{'file_path':str(tmp_path/'app.py')})) is None


@pytest.mark.parametrize('tool,args',[
    ('read',{'file_path':'../secret'}),('write',{'file_path':'../file','content':'bad'}),
    ('bash',{'command':'python -c "print(1)"'}),('sql_execute',{'sql':'select 1'}),
    ('glob',{'pattern':'../*'}),('write',{'file_path':'test_public.py'}),
    ('edit',{'file_path':'seeds/orders.csv'}),('tool_search',{'query':'sql'}),
])
def test_guard_blocks_disallowed_operations(tmp_path,tool,args):
    with pytest.raises(ValueError):
        guard.decide(event(tmp_path,tool,args))


def test_guard_rewrites_tests_into_container(tmp_path):
    result=guard.decide(event(tmp_path,'bash',{'command':'python -m pytest -q'}))
    assert '--network none' in result['command']
    assert 'readonly' in result['command']
    assert '/candidate' in result['command']


def test_guard_rejects_symlink_escape(tmp_path):
    root=tmp_path/'candidate'
    root.mkdir()
    (root/'outside').symlink_to(tmp_path/'secret')
    with pytest.raises(ValueError):
        guard.decide(event(root,'read',{'file_path':'outside'}))


def test_structured_errors_are_retained(tmp_path):
    path=tmp_path/'events.jsonl'
    path.write_text('noise\n{"type":"result","is_error":true}\n')
    assert events(path)==[{'type':'result','is_error':True}]


def test_only_c_contains_ponytail():
    assert '# Ponytail' not in prompt_for('python-format','A')
    assert '# Ponytail' not in prompt_for('python-format','B')
    assert '# Ponytail' in prompt_for('python-format','C')
    assert '## 2. Simplicity First' in prompt_for('python-format','B')
