"""Read-only CoCo inference probe. Saves evidence without exposing credentials."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="inference-v2")
    parser.add_argument("--connection", default=os.environ.get("BENCH_COCO_CONNECTION", "default"))
    parser.add_argument("--prompt", default="Do not call tools. Return only PREFLIGHT_OK.")
    parser.add_argument("--guard", action="store_true")
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        parser.error("name must be alphanumeric with optional hyphens")
    workdir = ROOT / "runs" / args.name
    workdir.mkdir(parents=True, exist_ok=True)
    command = [
        str(Path.home() / ".local/bin/cortex"),
        "--connection", args.connection, "--workdir", str(workdir),
        "--setting-sources", "", "--config", str(ROOT / "git/instructions/base-settings.json"),
        "--only-explicit-skills",
        "--only-explicit-plugins", "--only-explicit-profiles",
        "--no-mcp", "--no-auto-update", "--sql-read-only",
        "--model", "claude-opus-5-5", "--effort", "medium",
        "--max-turns", "2", "--output-format", "stream-json",
        "--disallowed-tools", "sql_execute", "bash", "task", "tool_search", "direct_tool_calling", "curator", "web_fetch", "web_search",
        "--print", args.prompt
    ]
    if args.guard:
        command += ["--plugin-dir", str(ROOT/'git/runner/guard-plugin'), '--allowed-tools', 'read', 'write', 'edit', 'glob', 'grep']
        command[command.index('--max-turns') + 1] = '5'
    started = time.monotonic()
    output_path = ROOT / "research" / f"{args.name}.stdout.jsonl"
    error_path = ROOT / "research" / f"{args.name}.stderr.txt"
    if output_path.exists():
        parser.error("probe already exists; use a new name to preserve evidence")
    with output_path.open("w") as output, error_path.open("w") as error:
        process = subprocess.Popen(command, stdout=output, stderr=error, start_new_session=True)
        try:
            status = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            status = "timeout"
    result = {"command": command, "status": status, "seconds": round(time.monotonic()-started, 2)}
    events = []
    for line in output_path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    result["agent_results"] = [event for event in events if event.get("type") == "result"]
    result["passed"] = status == 0 and bool(result["agent_results"]) and not result["agent_results"][-1].get("is_error", True)
    (ROOT / "research" / f"{args.name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
