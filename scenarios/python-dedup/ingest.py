import csv
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
