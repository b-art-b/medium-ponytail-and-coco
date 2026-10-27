import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluator.local import evaluate
from scenarios.fixtures import SCENARIOS, materialize

LOCAL = [name for name, scenario in SCENARIOS.items() if scenario['kind'] in {'python', 'streamlit'}]

@pytest.mark.parametrize('name', LOCAL)
def test_starter_public_checks_pass(name, tmp_path):
    root = materialize(name, tmp_path / name)
    run = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(root / 'test_public.py')], cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr

@pytest.mark.parametrize('name', LOCAL)
def test_starter_fails_acceptance(name, tmp_path):
    root = materialize(name, tmp_path / name)
    with pytest.raises((AssertionError, ValueError, KeyError)):
        evaluate(name, root)

@pytest.mark.parametrize('name', LOCAL)
def test_reference_passes_acceptance(name, tmp_path):
    root = materialize(name, tmp_path / name, reference=True)
    evaluate(name, root)

@pytest.mark.parametrize('name', LOCAL)
def test_mutated_reference_is_rejected(name, tmp_path):
    root = materialize(name, tmp_path / name, reference=True)
    target = root / SCENARIOS[name]['target']
    text = target.read_text()
    if name == 'python-format':
        text = text.replace('if line.strip()', 'if False')
    elif name == 'python-dedup':
        text = text.replace('merged[row["order_id"]] = row', 'merged.setdefault(row["order_id"], row)')
    else:
        text = text.replace("visible['net_cents'].sum()", "orders['net_cents'].sum()")
    target.write_text(text)
    with pytest.raises((AssertionError, ValueError, KeyError)):
        evaluate(name, root)


def test_fixture_export_does_not_contain_reference(tmp_path):
    root = materialize('python-format', tmp_path / 'candidate')
    assert set(path.name for path in root.iterdir()) == {'ingest.py', 'test_public.py', 'TASK.md'}
    with pytest.raises(FileExistsError):
        materialize('python-format', root)
