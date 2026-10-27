from ingest import canonical, merge_orders


def test_canonical():
    assert canonical({"order_id": " a ", "order_day": "2026-01-01", "amount_cents": "123"})["amount_cents"] == 123


def test_empty_merge():
    assert merge_orders([], []) == []
