from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_initial_state():
    app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run(timeout=15)
    assert not app.exception
    assert app.metric[0].value == "28.00"
    assert app.metric[1].value == "3"
