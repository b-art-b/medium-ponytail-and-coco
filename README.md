# Ponytail CoCo benchmark

Status: complete. 72 scored runs (8 tasks x 3 arms x 3 repetitions) on CoCo CLI 1.2.18, `claude-opus-5-5`, effort medium. Results in `../results/summary.json`, article in `../article.md`. No commits or pushes.

## Arms

- **A** stock CoCo: `--setting-sources ''`, `instructions/base-settings.json` (memory and instruction patterns off), only-explicit skills/plugins/profiles, no MCP.
- **B** A plus prompt snapshot `instructions/baseline.md` (global AGENTS.md + lean-build, surgical-patch, verify-and-stop).
- **C** B plus `instructions/ponytail.md` (upstream `skills/ponytail/SKILL.md` at `09c434ab73ca43761c5d8b0c5d341926c2fba710`).

B and C are delivered as prompt text, not as installed plugins. Hashes in `instructions/arms.json`.

## Contents

- `scenarios/fixtures.py`: eight synthetic tasks (Python ingestion, Streamlit, dbt, Dynamic Tables), starters and evaluator-only references. `scenarios/<name>/` and `manifest.json` are the exported starters.
- `evaluator/local.py`: Python and Streamlit (`AppTest`) behavioral checks.
- `evaluator/live.py`: Dynamic Table and dbt checks against Snowflake via `snow` CLI with a scoped service user; dbt runs in Docker. dbt evaluation seeds, builds, adds hidden fresh rows, then rebuilds (`hidden='build'`, used for the matrix) or rebuilds models only (`hidden='run'`, used by `runner/rescore_dbt.py`).
- `runner/guard-plugin/`: per-run `PreToolUse` hook. Absolute paths inside the candidate only, protected inputs, the single allowed shell command `python -m pytest -q` rewritten to a network-less read-only container (`runner/Dockerfile`).
- `runner/run.py --phase pilot-v2|matrix`: executes runs, writes `../results/<phase>/<id>/`.
- `runner/rescore_dbt.py`: secondary dbt scoring, `../results/dbt-rescore.json`.
- `runner/analyze.py`: `../results/summary.json` (strict and `models_only_dbt` blocks) and `all-runs.json`.
- `runner/validate_live.py`, `runner/validate_mutations.py`: reference-passes / mutation-fails checks (`../results/live-validation-v4.json`, all 8 expected).
- `runner/provision.py`, `service_user.py`, `snow.py`: temporary Snowflake resources on the `blog` connection. All removed after the run (see `../research/database-state.json`).

## Notes

- `results/summary.json` and `results/dbt-rescore.json` hold the aggregated numbers used in the article. Raw transcripts are not published because they contain local paths.

- The parent path contains a colon: call `.venv/bin/python` directly (`uv run` fails) and use Docker `--mount`, not `-v`.
- `.venv/bin/python -m pytest tests -q`: 30 tests pass.
- Configuration via environment variables: `BENCH_ACCOUNT` (`ORG-ACCOUNT` of a dedicated test account), `BENCH_ACCOUNT_LOCATOR`, `BENCH_USER`, `BENCH_SNOW_CONNECTION` (snow CLI connection for live SQL), `BENCH_COCO_CONNECTION` (connection for CoCo inference) and `BENCH_BUNDLED_SKILLS` (CoCo bundled skills folder, read-only for the agent).
- The temporary database, role, service user and key were deleted on 2026-10-20. Re-running live checks requires `runner/provision.py` and `runner/service_user.py` again.
