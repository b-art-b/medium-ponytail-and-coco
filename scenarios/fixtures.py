"""Synthetic fixture definitions. Reference patches are evaluator-only data.

materialize() exports only the starter and public prompt, never a solution.
SQL fixtures are prepared but require live Snowflake validation before freezing.
"""
from pathlib import Path
import json

INGEST = '''import csv
from datetime import date
import json
from pathlib import Path


def canonical(row):
    order_id = str(row["order_id"]).strip()
    if not order_id:
        raise ValueError("order_id required")
    order_day = date.fromisoformat(row["order_day"]).isoformat()
    amount = int(row["amount_cents"])
    if amount < 0:
        raise ValueError("amount_cents must be nonnegative")
    return {"order_id": order_id, "order_day": order_day, "amount_cents": amount}


def load_orders(path):
    path = Path(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("unsupported format")
    with path.open(newline="", encoding="utf-8") as handle:
        return [canonical(row) for row in csv.DictReader(handle)]


def merge_orders(existing, incoming):
    validated = [canonical(row) for row in incoming]
    return [dict(row) for row in existing] + validated
'''
JSON_REF = '''    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [canonical(json.loads(line)) for line in handle if line.strip()]
    if path.suffix.lower() != ".csv":
'''
MERGE_REF = '''    merged = {row["order_id"]: dict(row) for row in existing}
    for row in validated:
        merged[row["order_id"]] = row
    return list(merged.values())
'''
PUBLIC_INGEST = '''from ingest import canonical, merge_orders


def test_canonical():
    assert canonical({"order_id": " a ", "order_day": "2026-01-01", "amount_cents": "123"})["amount_cents"] == 123


def test_empty_merge():
    assert merge_orders([], []) == []
'''

DATA = [
    {"order_id": "a", "category": "Books", "region": "North", "gross_cents": 1000, "refund_cents": 200},
    {"order_id": "b", "category": "Books", "region": "South", "gross_cents": 500, "refund_cents": 500},
    {"order_id": "c", "category": "Games", "region": "North", "gross_cents": 2000, "refund_cents": 0},
]
APP_HEAD = '''from pathlib import Path
import pandas as pd
import streamlit as st

st.title("Retail sales")
orders = pd.read_json(Path(__file__).with_name("orders.json"))
orders["net_cents"] = orders["gross_cents"] - orders["refund_cents"]
'''
FILTERS = '''category = st.selectbox("Category", ["All", "Books", "Games", "Clothing"], key="category")
visible = orders if category == "All" else orders[orders["category"] == category]
'''
DISPLAY = '''st.metric("Net revenue", f"{visible['net_cents'].sum() / 100:.2f}")
st.metric("Orders", str(len(visible)))
st.dataframe(visible, hide_index=True, alt="Orders matching the current category")
if visible.empty:
    st.info("No matching orders")
'''
APP_FILTER = APP_HEAD + 'visible = orders\n' + DISPLAY
APP_TOTALS = APP_HEAD + FILTERS + DISPLAY.replace("visible['net_cents'].sum()", "orders['net_cents'].sum()")
PUBLIC_APP = '''from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_initial_state():
    app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run(timeout=15)
    assert not app.exception
    assert app.metric[0].value == "28.00"
    assert app.metric[1].value == "3"
'''

DBT_PROJECT = '''name: retail_benchmark
version: '1.0.0'
config-version: 2
profile: retail_benchmark
model-paths: [models]
seed-paths: [seeds]
models:
  retail_benchmark:
    +materialized: table
'''
ORDERS_CSV = 'order_id,customer_id,order_day,gross_cents\na,c1,2026-01-01,1000\nb,c2,2026-01-01,500\nc,c1,2026-01-02,2000\n'
REFUNDS_CSV = 'refund_id,order_id,refund_cents\nr1,a,150\nr2,a,50\nr3,b,500\n'
CUSTOMERS_CSV = 'customer_id,version,region\nc1,1,Old\nc1,2,North\nc2,1,South\n'
STG = "select order_id, customer_id, order_day::date as order_day, gross_cents::number(18,0) as gross_cents from {{ ref('orders') }}\n"
CURRENT_CUSTOMERS = "select customer_id, region from {{ ref('customers') }} qualify row_number() over (partition by customer_id order by version desc) = 1\n"
DAILY = "select order_day, sum(gross_cents) as net_cents from {{ ref('stg_orders') }} group by order_day\n"
DAILY_REF = '''with refunds_by_order as (
    select order_id, sum(refund_cents) as refund_cents
    from {{ ref('refunds') }} group by order_id
)
select o.order_day, sum(o.gross_cents - coalesce(r.refund_cents, 0)) as net_cents
from {{ ref('stg_orders') }} o
left join refunds_by_order r on o.order_id = r.order_id
group by o.order_day
'''
REGIONAL = '''select c.region, sum(o.gross_cents) as gross_cents
from {{ ref('stg_orders') }} o
join {{ ref('customers') }} c on o.customer_id = c.customer_id
group by c.region
'''
SCHEMA = '''version: 2
models:
  - name: stg_orders
    columns:
      - name: order_id
        data_tests: [unique, not_null]
  - name: current_customers
    columns:
      - name: customer_id
        data_tests: [unique, not_null]
'''

DT_BASE = '''-- Evaluator supplies the isolated database/schema and uses COMPUTE_WH.
CREATE DYNAMIC TABLE clean_orders
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_id, order_day, region, gross_cents - COALESCE(refund_cents, 0) AS net_cents
FROM raw_orders;
'''
DT_DAILY = '''CREATE DYNAMIC TABLE daily_sales
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_day, SUM(net_cents) AS net_cents FROM clean_orders GROUP BY order_day;
'''
DT_REGION = '''CREATE DYNAMIC TABLE regional_sales
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_day, region, SUM(net_cents) AS net_cents
FROM clean_orders GROUP BY order_day, region;
'''
DT_WRONG = '''CREATE DYNAMIC TABLE daily_sales
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_day, SUM(gross_cents) AS net_cents
FROM raw_orders WHERE refund_cents = 0 GROUP BY order_day;
'''


def dbt_files():
    return {"dbt_project.yml": DBT_PROJECT, "seeds/orders.csv": ORDERS_CSV,
            "seeds/refunds.csv": REFUNDS_CSV, "seeds/customers.csv": CUSTOMERS_CSV,
            "models/stg_orders.sql": STG, "models/current_customers.sql": CURRENT_CUSTOMERS,
            "models/daily_revenue.sql": DAILY, "models/regional_revenue.sql": REGIONAL,
            "models/schema.yml": SCHEMA}


SCENARIOS = {
    "python-format": {
        "kind": "python", "target": "ingest.py",
        "prompt": "Extend load_orders(path) to support UTF-8 .jsonl as well as CSV (case-insensitive suffix). Ignore blank JSONL lines. Each nonblank line must be an object with the same validation and canonical output as CSV. Reject malformed rows and unsupported formats, preserve order and the existing API, and do not change merge_orders. Include focused tests. Work only in this project.",
        "files": {"ingest.py": INGEST, "test_public.py": PUBLIC_INGEST},
        "reference": INGEST.replace('    if path.suffix.lower() != ".csv":\n', JSON_REF),
    },
    "python-dedup": {
        "kind": "python", "target": "ingest.py",
        "prompt": "Fix merge_orders(existing, incoming): one record per order_id, with the last incoming value winning (corrections replace previous values). Preserve original order for existing IDs, append new IDs in first-seen order. Do not mutate either input, including on error. Validate ALL incoming rows before returning. Preserve load_orders behavior and API. Include focused regression tests. Work only in this project.",
        "files": {"ingest.py": INGEST, "test_public.py": PUBLIC_INGEST},
        "reference": INGEST.replace('    return [dict(row) for row in existing] + validated\n', MERGE_REF),
    },
    "streamlit-filter": {
        "kind": "streamlit", "target": "app.py",
        "prompt": "Add a Category selectbox (key category) with All, Books, Games, Clothing. Default All. Both metrics and the table must reflect the selected category. For no matches retain the empty table, show zero metrics and the information message No matching orders. Preserve title, monetary formatting and data columns. Include AppTest coverage. No network access or data edits.",
        "files": {"app.py": APP_FILTER, "orders.json": json.dumps(DATA), "test_public.py": PUBLIC_APP},
        "reference": APP_HEAD + FILTERS + DISPLAY,
    },
    "streamlit-totals": {
        "kind": "streamlit", "target": "app.py",
        "prompt": "Fix Net revenue: it must always equal the sum of gross_cents minus refund_cents for the visible orders, including fully refunded and empty selections. Preserve existing widgets (including their keys), title, table, two-decimal monetary formatting and empty state. Include an AppTest regression exercising category changes and a return to All. No network access or data edits.",
        "files": {"app.py": APP_TOTALS, "orders.json": json.dumps(DATA), "test_public.py": PUBLIC_APP},
        "reference": APP_HEAD + FILTERS + DISPLAY,
    },
    "dbt-refunds": {
        "kind": "dbt", "target": "models/daily_revenue.sql",
        "prompt": "Fix daily_revenue to produce one row per order_day and net_cents = gross less ALL refunds attached to orders on that day. Multiple partial refunds are additive; unrefunded orders retain gross and fully refunded orders contribute zero. Attribute refunds to order day. Do not change the unrelated regional_revenue model or seed inputs. Add appropriate dbt tests. The evaluator runs seed and build in an isolated Snowflake schema; credentials are not included.",
        "files": dbt_files(), "reference": DAILY_REF,
    },
    "dbt-join": {
        "kind": "dbt", "target": "models/regional_revenue.sql",
        "prompt": "Fix regional_revenue to count each order once using its customer's latest dimension version (highest version number). Preserve columns region/gross_cents, inner-join behavior for unknown customers, and unrelated daily_revenue behavior. Do not change seed inputs. Add dbt regression tests. The evaluator runs seed and build in an isolated Snowflake schema; credentials are not included.",
        "files": dbt_files(), "reference": REGIONAL.replace("ref('customers')", "ref('current_customers')"),
    },
    "dt-region": {
        "kind": "dynamic-table", "target": "pipeline.sql",
        "prompt": "Extend pipeline.sql with a regional_sales Dynamic Table: order_day, region, net_cents, grouped by day/region from existing cleaned orders. Preserve clean_orders and daily_sales behavior and existing refresh configuration. Use only raw_orders and existing pipeline objects in the current isolated schema; no database/schema/role creation. Evaluator supplies COMPUTE_WH, seed data and manual refreshes. Add a local check or test for your new logic. Do not access a real account directly.",
        "files": {"pipeline.sql": DT_BASE + DT_DAILY},
        "reference": DT_BASE + DT_DAILY + DT_REGION,
    },
    "dt-corrections": {
        "kind": "dynamic-table", "target": "pipeline.sql",
        "prompt": "Fix daily_sales so net_cents includes all current orders, subtracting refunds (NULL means zero), including fully and partially refunded orders. Must reflect insert/update/delete changes after manual refresh without filtering out corrected or historical orders. Preserve clean_orders, daily_sales columns and existing refresh configuration. Only current-schema pipeline objects and raw_orders are permitted. Evaluator supplies COMPUTE_WH and raw rows; do not access a real account directly. Add a local check or test.",
        "files": {"pipeline.sql": DT_BASE + DT_WRONG},
        "reference": DT_BASE + DT_DAILY,
    },
}


def materialize(name, destination, reference=False):
    """Create a fresh fixture; refuses to overwrite an existing directory."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    scenario = SCENARIOS[name]
    for relative, text in scenario["files"].items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (destination / "TASK.md").write_text(scenario["prompt"] + "\n")
    if reference:
        (destination / scenario["target"]).write_text(scenario["reference"])
    return destination
