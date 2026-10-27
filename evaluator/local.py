"""Behavioral acceptance oracle for the four local scenarios."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile


def check_python(name, root):
    spec = importlib.util.spec_from_file_location("candidate_ingest", root / "ingest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = {"order_id": "a", "order_day": "2026-01-01", "amount_cents": 100}
    if name == "python-format":
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path = Path(temporary) / "orders.JSONL"
            path.write_text(json.dumps(first) + '\n\n' + json.dumps({**first, "order_id": "雪", "amount_cents": "200"}) + '\n')
            assert module.load_orders(path) == [first, {**first, "order_id": "雪", "amount_cents": 200}]
            for invalid in ['{', '[]', '{}', json.dumps({**first, 'amount_cents': -1}), json.dumps({**first, 'order_day': 'bad'})]:
                path.write_text(json.dumps(first) + '\n' + invalid)
                try:
                    module.load_orders(path)
                except (ValueError, TypeError, KeyError):
                    pass
                else:
                    raise AssertionError(f"accepted invalid JSONL row: {invalid}")
            path.write_text('\n\n')
            assert module.load_orders(path) == []
            csv_path = Path(temporary) / "orders.csv"
            csv_path.write_text('order_id,order_day,amount_cents\na,2026-01-01,100\n')
            assert module.load_orders(csv_path) == [first]
    else:
        existing = [first, {**first, "order_id": "b"}]
        incoming = [{**first, "amount_cents": "250"}, {**first, "order_id": "c"}, {**first, "amount_cents": "300"}]
        snapshot = copy.deepcopy((existing, incoming))
        expected = [{**first, "amount_cents": 300}, existing[1], incoming[1]]
        result = module.merge_orders(existing, incoming)
        assert result == expected
        assert module.merge_orders(result, incoming) == expected
        assert (existing, incoming) == snapshot
        assert module.merge_orders([], []) == []
        try:
            module.merge_orders(existing, incoming + [{**first, "amount_cents": -1}])
        except ValueError:
            pass
        else:
            raise AssertionError("invalid batch accepted")
        assert (existing, incoming) == snapshot
        result[0]["amount_cents"] = 999
        assert existing[0]["amount_cents"] == 100


def check_streamlit(root):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(root / "app.py")).run(timeout=20)
    assert not app.exception
    for category, amount, count in [("All", "28.00", 3), ("Books", "8.00", 2), ("Games", "20.00", 1), ("Clothing", "0.00", 0), ("All", "28.00", 3)]:
        app.selectbox(key="category").select(category).run(timeout=20)
        assert not app.exception
        assert app.metric[0].value == amount
        assert app.metric[1].value == str(count)
        frame = app.dataframe[0].value
        assert len(frame) == count
        assert f"{(frame['gross_cents'] - frame['refund_cents']).sum() / 100:.2f}" == amount
        if category != "All":
            assert all(frame["category"] == category)
        if count == 0:
            assert any(message.value == "No matching orders" for message in app.info)
        else:
            assert not app.info


def evaluate(name, root):
    root = Path(root)
    if name.startswith("python-"):
        check_python(name, root)
    elif name.startswith("streamlit-"):
        check_streamlit(root)
    else:
        raise ValueError("Live Snowflake evaluator required; local checks are not a substitute")
