"""Small interface parts: bookmarks overflow, download ring, address text, loading line, tab previews."""

import http.server
import os
import threading
import time

import pytest

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")   # folder for screenshots, optional


def test_bookmarks_overflow_button(run_ike):
    out = run_ike("""
        import os
        from PyQt6.QtGui import QIcon

        def steps(ike, qapp, out):
            yield 400
            win = ike.windows[0]
            win.resize(1000, 700)
            bar = win.bookbar
            bar.show()
            marks = [(QIcon(), "Bookmark number %d" % i, "https://example.org/%d" % i)
                     for i in range(40)]
            bar.set_marks(marks, lambda u: None)
            yield 400
            more = bar._more
            out["text"] = more.text()
            out["icon"] = not more.icon().isNull()
            out["size"] = [more.width(), more.height()]
            out["visible"] = bar._more_action.isVisible()
            out["in_bar"] = sum(a.isVisible() for a in bar._marks)
            out["in_menu"] = len(bar._menu.actions())
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                bar.grab().save(os.path.join(shots, "bookmarks-overflow.png"))
            win.resize(8000, 700)
            yield 400
            if win.width() < 8000:
                # the window manager kept the window within the screen: make the marks fit instead
                bar.set_marks(marks[:2], lambda u: None)
                yield 400
            out["wide_visible"] = bar._more_action.isVisible()
    """, settings={"bookmarks_bar": "always"}, env={"IKE_TEST_SHOTS": SHOTS})
    # 1.1.25: KDE's double arrow in a square button, no "»" text (tests/test_more_arrows.py)
    assert out["text"] == ""
    assert out["icon"] is True and out["size"] == [26, 26]
    assert out["visible"]
    assert out["in_bar"] + out["in_menu"] == 40 and out["in_menu"] > 0
    assert out["wide_visible"] is False


@pytest.fixture
def slow_server():
    """Serves /file.bin (200 kB) in pieces over about two seconds."""
    size = 200 * 1024

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=file.bin")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            for _ in range(20):
                self.wfile.write(b"x" * (size // 20))
                self.wfile.flush()
                time.sleep(0.1)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/file.bin" % httpd.server_address[1]
    httpd.shutdown()


def test_download_progress_ring(run_ike, slow_server, tmp_path):
    out = run_ike("""
        import os
        from PyQt6.QtCore import QSize, QUrl
        from PyQt6.QtGui import QColor, QGuiApplication, QPalette

        def colours(win):
            img = win.act_downloads.icon().pixmap(QSize(32, 32)).toImage()
            green = blue = 0
            for x in range(img.width()):
                for y in range(img.height()):
                    c = QColor(img.pixel(x, y))
                    if c.alpha() < 120:
                        continue
                    if c.green() > 140 and c.red() < 90 and c.blue() < 130:
                        green += 1
                    hl = QGuiApplication.palette().color(QPalette.ColorRole.Highlight)
                    if abs(c.red() - hl.red()) + abs(c.green() - hl.green()) + abs(c.blue() - hl.blue()) < 40:
                        blue += 1
            return green, blue

        def steps(ike, qapp, out):
            yield 400
            win = ike.windows[0]
            out["start"] = ike._dl_state[0]
            out["start_colours"] = colours(win)
            win.current_view().page().download(QUrl(%r))
            fractions = []
            for _ in range(8):
                yield 200
                if ike._dl_state[0] == "active":
                    fractions.append(ike._dl_state[1])
            out["fractions"] = fractions
            out["active_colours"] = colours(win)
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                win.act_downloads.icon().pixmap(QSize(64, 64)).save(os.path.join(shots, "download-active.png"))
            for _ in range(30):
                yield 200
                if ike._dl_state[0] == "done":
                    break
            out["end"] = ike._dl_state[0]
            out["done_colours"] = colours(win)
            if shots:
                win.act_downloads.icon().pixmap(QSize(64, 64)).save(os.path.join(shots, "download-done.png"))
            second = ike.new_window()
            yield 300
            out["new_window_state"] = colours(second)[0] > 0
            ike.show_downloads()
            yield 300
            out["after_open"] = ike._dl_state[0]
            out["after_open_colours"] = colours(win)
            out["file"] = os.path.getsize(os.path.join(%r, "file.bin"))
    """ % (slow_server, str(tmp_path / "dl")),
        settings={"download_dir": str(tmp_path / "dl"), "ask_download_location": False},
        env={"IKE_TEST_SHOTS": SHOTS})
    assert out["start"] == "idle" and out["start_colours"][0] == 0
    fr = [f for f in out["fractions"] if f is not None]
    assert fr and any(0 < f < 1 for f in fr) and fr == sorted(fr), out["fractions"]
    assert out["active_colours"][1] > 5
    assert out["end"] == "done" and out["done_colours"][0] > 10
    assert out["new_window_state"]
    assert out["after_open"] == "idle" and out["after_open_colours"][0] == 0
    assert out["file"] == 200 * 1024


def test_address_bar_domain_highlight(run_ike):
    out = run_ike("""
        import os
        from PyQt6.QtGui import QColor

        def darkest(img, x0, x1):
            best = 255 * 3
            for x in range(max(0, x0), min(img.width(), x1)):
                for y in range(img.height()):
                    c = QColor(img.pixel(x, y))
                    best = min(best, c.red() + c.green() + c.blue())
            return best

        def measure(bar, text):
            spans = {}
            start, length = bar.domain_span()
            for name, (a, b) in (("scheme", (0, start - 3)), ("host", (start, start + length)),
                                 ("path", (start + length + 1, len(text)))):
                bar.setCursorPosition(a)
                xa = bar.cursorRect().center().x()
                bar.setCursorPosition(b)
                xb = bar.cursorRect().center().x()
                spans[name] = (xa + 1, xb - 1)
            # only the text: not the shield and the field's buttons on the right (1.1.10)
            end = min([w.x() for w in bar.children() if w.isWidgetType() and w.isVisible()
                       and w.x() > bar.width() // 2] or [bar.width()])
            spans = {k: (a, min(b, end - 2)) for k, (a, b) in spans.items()}
            bar.setCursorPosition(0)
            img = bar.grab().toImage()
            return {k: darkest(img, a, b) for k, (a, b) in spans.items()}

        def steps(ike, qapp, out):
            yield 400
            win = ike.windows[0]
            bar = win.urlbar
            text = "https://www.example.org/some/long/path?query=1"
            win.current_view().setFocus()
            bar.setText(text)
            bar.setCursorPosition(0)
            yield 100
            out["span"] = bar.domain_span()
            out["unfocused"] = measure(bar, text)
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                bar.grab().save(os.path.join(shots, "urlbar-domain.png"))
            # while typing in the bar everything is normal text
            bar.setFocus()
            yield 100
            out["focus_has"] = bar.hasFocus()
            out["focused"] = measure(bar, text)
            out["text_kept"] = bar.text() == text
            out["search_span"] = bar.domain_span("hello world")
            out["idn"] = bar.domain_span("http://user@xn--80ak6aa92e.com:8080/a")
    """, env={"IKE_TEST_SHOTS": SHOTS})
    assert out["span"] == [8, 15]
    u = out["unfocused"]
    assert u["path"] > u["host"] + 150 and u["scheme"] > u["host"] + 150, u
    if out["focus_has"]:          # an offscreen window does not always take the focus
        f = out["focused"]
        assert abs(f["path"] - f["host"]) < 60, f
    assert out["text_kept"]
    assert out["search_span"] is None
    assert out["idn"] == [12, 18]


@pytest.fixture
def slow_page():
    """Serves an HTML page whose body arrives over about four seconds."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>slow</title><img src='/missing.png'>")
            for i in range(20):
                self.wfile.write(b"<p>part %d</p>" % i + b" " * 2048)
                self.wfile.flush()
                time.sleep(0.2)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % httpd.server_address[1]
    httpd.shutdown()


def test_loading_line(run_ike, slow_page):
    out = run_ike("""
        import os
        from PyQt6.QtGui import QColor

        def steps(ike, qapp, out):
            yield 400
            for _ in range(50):                 # the new tab page has finished loading
                if not getattr(ike.windows[0].current_view(), "loading", False):
                    break
                yield 100
            yield 200
            from ike import themes
            ike.config["ui_scheme"] = "theme:ike"
            themes.apply(ike.config)
            win = ike.windows[0]
            line = win.loading_line
            out["idle_visible"] = line.isVisible()
            view = win.add_tab(%r)
            seen = []
            for _ in range(8):
                yield 150
                seen.append((line.isVisible(), round(line.value, 2)))
            out["seen"] = seen
            out["geometry"] = [line.y() == win.content.y(), line.width() == win.content.width(),
                               line.height()]
            img = line.grab().toImage()
            # 1.1.23: a flat bar as Breeze's (1.1.3 to 1.1.22: a soft start), the
            # accent colour from its start to where the page has got
            end = int(line.INSET + (line.width() - 2 * line.INSET) * line.value)
            out["colour"] = QColor(img.pixel(max(3, end - 8), 3)).name()
            out["flat"] = QColor(img.pixel(4, 3)).name() == out["colour"]
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                win.grab().save(os.path.join(shots, "loading-line.png"))
            # another tab that is not loading: no line
            win.set_current(win.views[0])
            yield 100
            out["other_tab"] = line.isVisible()
            win.set_current(view)
            yield 100
            out["back_tab"] = line.isVisible()
            for _ in range(30):
                yield 200
                if not view.loading:
                    break
            yield 600
            out["after"] = line.isVisible()
            out["title"] = view.title()
    """ % slow_page, env={"IKE_TEST_SHOTS": SHOTS})
    assert out["idle_visible"] is False
    shown = [v for vis, v in out["seen"] if vis]
    assert shown, out["seen"]
    assert out["geometry"] == [True, True, 6]
    assert out["colour"] == "#19c3e6" and out["flat"] is True
    assert out["other_tab"] is False and out["back_tab"] is True
    assert out["after"] is False and out["title"] == "slow"


def test_tab_previews(run_ike):
    out = run_ike("""
        import os
        from PyQt6.QtCore import QPoint, QEvent
        from PyQt6.QtGui import QColor, QHelpEvent
        from PyQt6.QtWidgets import QApplication

        def tip(win, obj, pos):
            ev = QHelpEvent(QEvent.Type.ToolTip, pos, obj.mapToGlobal(pos))
            QApplication.sendEvent(obj, ev)

        def steps(ike, qapp, out):
            yield 400
            win = ike.windows[0]
            red = win.add_tab("data:text/html,<title>red</title><body style='background:%23d00000'>")
            yield 1200
            win.add_tab("data:text/html,<title>blue</title><body style='background:%230000d0'>")
            yield 1200
            out["has_preview"] = getattr(red, "preview", None) is not None
            pm = red.preview
            out["size"] = [pm.width(), pm.height()]
            c = QColor(pm.toImage().pixel(pm.width() // 2, pm.height() // 2))
            out["centre"] = [c.red(), c.green(), c.blue()]
            # rest the mouse on the red tab (not the current one)
            i = win.views.index(red)
            rect = win.tabbar.tabRect(i)
            tip(win, win.tabbar, rect.center())
            yield 200
            prev = win._preview
            out["shown"] = prev.isVisible()
            out["text"] = prev.text.text()
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                prev.grab().save(os.path.join(shots, "tab-preview.png"))
            QApplication.sendEvent(win.tabbar, QEvent(QEvent.Type.Leave))
            yield 100
            out["hidden_after_leave"] = not prev.isVisible()
            # the current tab shows its normal tooltip, no preview
            cur = win.views.index(win.current_view())
            tip(win, win.tabbar, win.tabbar.tabRect(cur).center())
            yield 100
            out["current_preview"] = prev.isVisible()
            # vertical tabs use the same preview
            ike.config["tabs_position"] = "vertical"
            win.apply_layout()
            yield 300
            r = win.vtabs.visualItemRect(win.vtabs.item(i))
            tip(win, win.vtabs.viewport(), r.center())
            yield 200
            out["vertical_shown"] = prev.isVisible() and prev.index == i
            # closing the tab drops its picture with it
            win.close_tab(red)
            yield 300
            out["tabs"] = len(win.views)
    """, env={"IKE_TEST_SHOTS": SHOTS})
    assert out["has_preview"]
    assert out["size"][0] == 240 and 60 < out["size"][1] <= 180
    r, g, b = out["centre"]
    assert r > 150 and g < 60 and b < 60, out["centre"]
    assert out["shown"] and "red" in out["text"]
    assert out["hidden_after_leave"]
    assert out["current_preview"] is False
    assert out["vertical_shown"]


@pytest.fixture
def weather_server():
    """Stand-in for Open-Meteo: records every request."""
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.startswith("/search"):
                body = {"results": [
                    {"name": "Rome", "latitude": 41.89193, "longitude": 12.51133,
                     "admin1": "Lazio", "country": "Italy"},
                    {"name": "Rome", "latitude": 34.25704, "longitude": -85.16467,
                     "admin1": "Georgia", "country": "United States"}]}
            else:
                body = {"current": {"temperature_2m": 12.4, "weather_code": 3}}
            data = __import__("json").dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1], seen
    httpd.shutdown()


WEATHER_STEPS = """
    import os, re

    def page_text(view, js, res, key):
        view.page().runJavaScript(js, lambda r: res.__setitem__(key, r))

    def steps(ike, qapp, out):
        yield 600
        win = ike.windows[0]
        view = win.current_view()
        res = {}
        page_text(view, "[document.getElementById('clock') && document.getElementById('clock').textContent,"
                        " document.getElementById('weather') && document.getElementById('weather').textContent]",
                  res, "before")
        yield 300
        out["before"] = res.get("before")
        # choose the city in Settings
        dlg = ike.show_settings(win, "general")
        yield 200
        dlg.city.setText("Rome")
        dlg._find_city()
        for _ in range(20):
            yield 100
            if dlg.city_results.count():
                break
        out["results"] = [dlg.city_results.itemText(i) for i in range(dlg.city_results.count())]
        dlg.apply()
        dlg.close()
        out["saved"] = [ike.config["weather_city"], ike.config["weather_lat"], ike.config["weather_lon"]]
        # the open new tab page gets the weather without reloading
        page_text(view, "window.__mark = 1", res, "mark")
        win.add_tab()
        for _ in range(30):
            yield 100
            if ike.weather.data:
                break
        yield 500
        page_text(view, "[document.getElementById('weather').textContent, window.__mark]", res, "after")
        yield 300
        out["after"] = res.get("after")
        page_text(win.current_view(), "document.getElementById('weather').textContent", res, "new")
        yield 300
        out["new_tab"] = res.get("new")
        shots = os.environ.get("IKE_TEST_SHOTS")
        if shots:
            win.grab().save(os.path.join(shots, "newtab-clock-weather.png"))
        # more new tabs within 30 minutes: no new request
        win.add_tab()
        yield 800
        win.add_tab()
        yield 800
        # switched off: nothing in the corner, nothing asked
        ike.config["newtab_clock"] = False
        ike.config["newtab_weather"] = False
        v2 = win.add_tab()
        yield 1000
        page_text(v2, "document.querySelector('.corner').innerHTML", res, "off")
        yield 300
        out["off"] = res.get("off")
"""


def test_newtab_clock_and_weather(run_ike, weather_server):
    base, seen = weather_server
    out = run_ike(WEATHER_STEPS, env={"IKE_TEST_WEATHER": base, "IKE_TEST_SHOTS": SHOTS})
    clock, weather = out["before"]
    assert clock and __import__("re").fullmatch(r"\d\d:\d\d( [AP]M)?", clock), clock
    assert weather == ""
    assert out["results"] == ["Rome, Lazio, Italy", "Rome, Georgia, United States"]
    assert out["saved"] == ["Rome", 41.89, 12.51]
    assert out["after"] == ["☁ 12 °C · Cloudy · Rome", 1]
    assert out["new_tab"] == "☁ 12 °C · Cloudy · Rome"
    searches = [p for p in seen if p.startswith("/search")]
    forecasts = [p for p in seen if p.startswith("/forecast")]
    assert len(searches) == 1 and "name=Rome" in searches[0]
    # only the rounded coordinates (and what to return) are sent, once; 1.1.25 asks the same request
    # for the few details too (wind direction, felt temperature, humidity, pressure, chance of precipitation)
    assert forecasts == ["/forecast?latitude=41.89&longitude=12.51&current=temperature_2m%2Cweather_code%2Cwind_speed_10m"
                         "%2Cwind_direction_10m%2Capparent_temperature%2Crelative_humidity_2m%2Cpressure_msl"
                         "%2Cprecipitation_probability"]
    assert out["off"] == ""
