"""Fail-closed candidate tool policy, loaded as a per-run PreToolUse hook."""
import json
import os
from pathlib import Path
import shlex
import sys


def decide(event):
    root = Path(event['cwd']).resolve()
    name = event.get('tool_name', '').lower()
    args = event.get('tool_input', {})
    if name in {'skill_view', 'skills_list', 'skill'}:
        return None
    if name in {'read', 'write', 'edit', 'glob', 'grep'}:
        value = args.get('file_path') if name in {'read', 'write', 'edit'} else args.get('path', '.')
        if not isinstance(value, str):
            raise ValueError('Missing path')
        target = (root / value).resolve()
        bundled = Path(os.environ.get('BENCH_BUNDLED_SKILLS', str(Path.home() / '.local/share/cortex/bundled_skills')))
        if name == 'read' and target.is_relative_to(bundled):
            return None
        if name in {'glob', 'grep'}:
            pattern = args.get('pattern', '') if name == 'glob' else args.get('include', '')
            if pattern.startswith('/') or '..' in Path(pattern).parts:
                raise ValueError('Pattern cannot escape candidate project')
        if not target.is_relative_to(root):
            raise ValueError('Only candidate project paths are accessible')
        if name in {'write', 'edit'} and (target.name in {'TASK.md', 'test_public.py', 'orders.json'} or 'seeds' in target.relative_to(root).parts):
            raise ValueError('Fixture inputs and public tests are immutable')
        # Tools may resolve omitted/relative paths against the parent IDE workspace.
        # Require explicit absolute paths rather than relying on that default.
        if not Path(value).is_absolute():
            raise ValueError('Use an explicit absolute candidate-project path')
        return None
    if name == 'bash':
        if args.get('command', '').strip() != 'python -m pytest -q':
            raise ValueError('Only python -m pytest -q is supported; it runs in an isolated container')
        command = ' '.join(shlex.quote(part) for part in [
            '/usr/local/bin/docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
            '--memory', '1g', '--cpus', '1', '--tmpfs', '/tmp:rw,nosuid,size=128m',
            '--mount', f'type=bind,source={root},target=/candidate,readonly', '-w', '/candidate',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'HOME=/tmp',
            'ponytail-benchmark-tests:local', 'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        ])
        return {'command': command, 'timeout_ms': 60000, 'description': 'Run tests in network-disabled synthetic sandbox'}
    raise ValueError(f'Tool {name} is not allowed in candidate sessions')


def main():
    try:
        event = json.load(sys.stdin)
        updated = decide(event)
        output = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}
        if updated is not None:
            output['hookSpecificOutput']['updatedInput'] = updated
        print(json.dumps(output))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
