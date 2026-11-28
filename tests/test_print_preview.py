"""Print preview (Unreleased): Print… (Ctrl+P, the menus, the page's menu)
shows the pages as they will be printed before the system's print window."""

STEPS = r'''
from PyQt6.QtCore import QUrl
from PyQt6.QtPrintSupport import QPrintPreviewDialog, QPrintPreviewWidget

def steps(ike, qapp, out):
    yield 300
    win = ike.windows[0]
    v = win.current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl.fromLocalFile(PAGE))
    while "ok" not in done:
        yield 20
    yield 300
    win.act_print.trigger()
    dlg = None
    for _ in range(100):
        yield 100
        dlg = getattr(win, "_print_preview", None)
        prev = dlg.findChild(QPrintPreviewWidget) if dlg is not None else None
        if prev is not None and prev.pageCount() > 0:
            break
    out["dialog"] = isinstance(dlg, QPrintPreviewDialog) and dlg.isVisible()
    out["pages"] = prev.pageCount() if prev is not None else 0
    out["title"] = dlg.windowTitle() if dlg is not None else ""
    out["modal"] = dlg.isModal() if dlg is not None else None
    out["ui_answers"] = True                  # the steps go on: the preview does not block I.K.E.
    # a second Print… replaces the first preview
    win.print_page()
    yield 800
    out["second"] = getattr(win, "_print_preview", None) is not dlg
    win._print_preview.close()
    yield 300
    out["closed"] = getattr(win, "_print_preview", None) is None
'''

PAGE = ("<!doctype html><meta charset=utf-8><title>Long page</title>"
        + "".join("<p>Paragraph %d of a page long enough for three sheets of paper.</p>" % i
                  for i in range(150)))


def test_print_shows_a_preview_first(run_ike, tmp_path):
    page = tmp_path / "long.html"
    page.write_text(PAGE, "utf-8")
    out = run_ike(("PAGE = %r\n" % str(page)) + STEPS, timeout=120)
    assert out["dialog"] is True
    assert out["pages"] >= 2, out
    assert "Long page" in out["title"]
    assert out["ui_answers"] and out["second"] and out["closed"]
