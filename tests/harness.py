"""Runs inside the real browser (loaded through IKE_TEST_HOOK).

The test script (IKE_TEST_SCRIPT) defines ``steps(ike, qapp, out)``: a
generator that yields the number of milliseconds to wait before it goes on,
so the event loop keeps running between checks. Whatever it puts in ``out``
is written as JSON to IKE_TEST_OUT, then the browser quits. An exception is
reported as out["error"].
"""

import json
import os
import traceback

from PyQt6.QtCore import QTimer

_script = os.environ["IKE_TEST_SCRIPT"]
_outfile = os.environ["IKE_TEST_OUT"]
_out = {}
_scope = {}
exec(compile(open(_script, encoding="utf-8").read(), _script, "exec"), _scope)
_gen = None


def _finish():
    with open(_outfile, "w", encoding="utf-8") as f:
        json.dump(_out, f, default=str)
    for w in list(ike.windows):            # noqa: F821  (given by the browser)
        w.close()
    QTimer.singleShot(200, qapp.quit)       # noqa: F821


def _step():
    try:
        wait = next(_gen)
    except StopIteration:
        _finish()
        return
    except Exception:
        _out["error"] = traceback.format_exc()
        _finish()
        return
    QTimer.singleShot(int(wait or 0), _step)


def _start():
    global _gen
    try:
        _gen = _scope["steps"](ike, qapp, _out)  # noqa: F821
    except Exception:
        _out["error"] = traceback.format_exc()
        _finish()
        return
    _step()


QTimer.singleShot(int(os.environ.get("IKE_TEST_DELAY", "300")), _start)
