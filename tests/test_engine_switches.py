"""Engine switches that take a protection away, and starting as root (1.1.18,
security audit F7 and F8).

A system-wide QTWEBENGINE_CHROMIUM_FLAGS (set for another program, or left
over) could switch off the sandbox, site isolation, web security or
certificate checks, or open remote control of the browser
(QTWEBENGINE_REMOTE_DEBUGGING), and I.K.E. followed silently. Started as root
it switched its sandbox off by itself. Now such switches are dropped and the
window says so; only IKE_ALLOW_UNSAFE_ENGINE=1 keeps them (and About and the
window show that protections are off). As root I.K.E. refuses to start unless
asked the same way. Graphics, video and speed switches are never touched.
"""

import os
import subprocess
import sys

import pytest
from conftest import APP

sys.path.insert(0, str(APP))
from ike import app as ike_app  # noqa: E402

DANGEROUS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox",
             "--disable-gpu-sandbox", "--single-process", "--no-zygote", "--disable-site-isolation-trials",
             "--disable-web-security", "--allow-running-insecure-content", "--ignore-certificate-errors",
             "--ignore-certificate-errors-spki-list=abc", "--remote-debugging-port=9222",
             "--remote-debugging-pipe", "--remote-debugging-address=0.0.0.0", "--remote-allow-origins=*",
             "--unsafely-treat-insecure-origin-as-secure=http://x.test", "--allow-file-access-from-files",
             "--reduce-security-for-testing"]
HARMLESS = ["--enable-features=VaapiVideoDecoder", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
            "--use-gl=egl", "--enable-smooth-scrolling", "--disable-gpu", "--force-dark-mode",
            "--js-flags=--max-old-space-size=512"]


def test_dangerous_switches_are_dropped_and_named():
    env = {"QTWEBENGINE_DISABLE_SANDBOX": "1", "QTWEBENGINE_REMOTE_DEBUGGING": "9222", "OTHER": "x"}
    out, named = ike_app._engine_safety(DANGEROUS + HARMLESS, env=env, allowed=False)
    assert out == HARMLESS, out                                   # graphics, video, speed: kept as they were
    assert set(named) == {d.split("=")[0] for d in DANGEROUS} | {"QTWEBENGINE_DISABLE_SANDBOX",
                                                                 "QTWEBENGINE_REMOTE_DEBUGGING"}
    assert env == {"OTHER": "x"}                                  # the variables are gone for the engine


def test_disabled_isolation_features_are_taken_out_of_a_list():
    out, named = ike_app._engine_safety(
        ["--disable-features=IsolateOrigins,site-per-process,OverlayScrollbar"], env={}, allowed=False)
    assert out == ["--disable-features=OverlayScrollbar"], out
    assert named == ["--disable-features=IsolateOrigins", "--disable-features=site-per-process"]
    out, _ = ike_app._engine_safety(["--disable-features=SitePerProcess"], env={}, allowed=False)
    assert out == []


def test_the_user_can_keep_them_on_purpose():
    env = {"QTWEBENGINE_DISABLE_SANDBOX": "1"}
    out, named = ike_app._engine_safety(["--no-sandbox", "--use-gl=egl"], env=env, allowed=True)
    assert out == ["--no-sandbox", "--use-gl=egl"] and env == {"QTWEBENGINE_DISABLE_SANDBOX": "1"}
    assert set(named) == {"--no-sandbox", "QTWEBENGINE_DISABLE_SANDBOX"}


def test_a_zero_or_empty_variable_is_not_a_switch():
    env = {"QTWEBENGINE_DISABLE_SANDBOX": "0", "QTWEBENGINE_REMOTE_DEBUGGING": ""}
    out, named = ike_app._engine_safety([], env=env, allowed=False)
    assert named == [] and env == {"QTWEBENGINE_DISABLE_SANDBOX": "0", "QTWEBENGINE_REMOTE_DEBUGGING": ""}


def test_root_is_refused_unless_asked(monkeypatch):
    monkeypatch.setattr(ike_app.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.delenv("IKE_ALLOW_UNSAFE_ENGINE", raising=False)
    assert ike_app.refuse_root() is True
    monkeypatch.setenv("IKE_ALLOW_UNSAFE_ENGINE", "1")
    assert ike_app.refuse_root() is False
    monkeypatch.setattr(ike_app.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.delenv("IKE_ALLOW_UNSAFE_ENGINE", raising=False)
    assert ike_app.refuse_root() is False


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() != 0, reason="only as root (the Arch container)")
def test_started_as_root_it_stops_and_says_why(tmp_path):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("IKE_", "QTWEBENGINE_"))}
    e.update(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "c"), XDG_DATA_HOME=str(tmp_path / "d"),
             XDG_CACHE_HOME=str(tmp_path / "k"), QT_QPA_PLATFORM="offscreen", IKE_NO_SINGLE="1")
    run = subprocess.run([sys.executable, str(APP / "ike_boot.py")], env=e, capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 1, (run.returncode, run.stderr[-800:])
    assert "does not start as root" in run.stderr and "IKE_ALLOW_UNSAFE_ENGINE=1" in run.stderr
    version = subprocess.run([sys.executable, str(APP / "ike_boot.py"), "--version"], env=e,
                             capture_output=True, text=True, timeout=60)
    assert version.returncode == 0 and "I.K.E." in version.stdout        # --version still answers


STEPS = r'''
def steps(ike, qapp, out):
    yield 500
    from ike.app import ENGINE_SAFETY, engine_safety_lines
    from ike.i18n import T
    out["kept"] = sorted(set(ENGINE_SAFETY["kept"]))
    out["lines"] = engine_safety_lines(T)
'''


def test_about_names_the_protections_switched_off_on_request(run_ike):
    if os.environ.get("IKE_TEST_SANDBOX") == "1":
        pytest.skip("this run has every protection on")
    out = run_ike(STEPS, timeout=60)
    assert "--no-sandbox" in out["kept"], out                 # the test harness asks for it on purpose
    assert any("IKE_ALLOW_UNSAFE_ENGINE" in line and "--no-sandbox" in line for line in out["lines"]), out
