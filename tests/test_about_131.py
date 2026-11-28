"""1.1.31 (the owner): Help -> About names only Dark Reader's lists, with their date, not a Dark Reader
version: since 1.1.30 only its lists are part of I.K.E."""

import json

from test_security import JS


def test_about_names_only_the_lists(run_ike):
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    out["text"] = ike.windows[0]._versions()
    yield 10
''', settings={"welcome_done": True}, timeout=60)
    from conftest import APP
    shipped = json.loads((APP / "ike" / "resources" / "darkreader-data.json").read_text("utf-8"))
    text = out["text"]
    assert "Dark Reader&#x27;s lists" in text or "Dark Reader's lists" in text, text
    assert shipped["lists_date"] in text
    assert shipped["version"] not in text and "Dark Reader — " not in text, text
