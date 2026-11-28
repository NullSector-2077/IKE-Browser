"""A file too large to be shown whole can be fixed from its excerpt at the failure (the drill, 2026-11-28).

ike/window.py (175 KB) never fits the reserves' budget of whole files; the reserves' fix of it was refused as
"not one of the files shown" every time. The files whose code at the failure is shown may be edited now; a file
neither shown nor excerpted still may not, and the text to replace must still appear exactly once."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("exc_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_excerpted_file_is_editable_and_nothing_else(tmp_path):
    reserve, context = load("autofix-reserve"), load("autofix-context")
    (tmp_path / "ike").mkdir()
    lines = 60000                                             # larger than the whole files any provider gets
    big = "".join("x%d = %d\n" % (i, i) for i in range(lines)) + "page.recentlyAudible()\n"
    assert len(big) > reserve.FILES_BUDGET
    (tmp_path / "ike" / "window.py").write_text(big)
    (tmp_path / "ike" / "other.py").write_text("y = 1\n")
    failure = ('Traceback (most recent call last):\n  File "/srv/ike/window.py", line %d, in tab\n'
               "AttributeError: 'QWebEnginePage' object has no attribute 'recentlyAudible'\n") % (lines + 1)
    text, related = context.build(tmp_path, failure, recent=False)
    assert related[0] == "ike/window.py"
    shown = reserve.files_shown(tmp_path, related)
    assert "ike/window.py" not in shown                       # too large to be shown whole
    editable = reserve.editable_files(shown, text, related)
    assert "ike/window.py" in editable and "ike/other.py" not in editable
    edit = {"file": "ike/window.py", "find": "%d  page.recentlyAudible()" % (lines + 1),
            "replace": "page.isRecentlyAudible()"}
    assert reserve.apply_edits(tmp_path, [edit], editable) == ["ike/window.py"]
    assert (tmp_path / "ike" / "window.py").read_text().endswith("page.isRecentlyAudible()\n")
    with pytest.raises(ValueError, match="not one of the files shown"):
        reserve.apply_edits(tmp_path, [{"file": "ike/other.py", "find": "y = 1", "replace": "y = 2"}], editable)
    # an excerpt heading of a file that is not among the files involved gives nothing
    assert "ike/other.py" not in reserve.editable_files({}, "### `ike/other.py`, lines 1-1 (the failure points at "
                                                         "line 1)\n", related)
