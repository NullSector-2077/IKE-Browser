"""tools/engine-report.py: what the engine of this system declares and what it
really decodes (tests/media holds one two-second clip per format: test data,
never packaged)."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)


def test_report_declared_and_decoded(tmp_path):
    out = tmp_path / "r.json"
    md = tmp_path / "r.md"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QTWEBENGINE_DISABLE_SANDBOX="1",
               HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "d"), XDG_CONFIG_HOME=str(tmp_path / "c"),
               XDG_CACHE_HOME=str(tmp_path / "k"))
    r = subprocess.run([sys.executable, str(ROOT / "tools/engine-report.py"), "--app", str(APP),
                        "--decode", str(ROOT / "tests/media"), "--json", str(out), "--markdown", str(md)],
                       env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    rep = json.loads(out.read_text("utf-8"))
    for key in ("system", "python", "qt", "pyqt", "qt_webengine", "chromium", "formats", "decoded"):
        assert key in rep, key
    declared, decoded = rep["formats"], rep["decoded"]
    assert set(declared) == set(decoded) == {"H.264", "AAC", "HEVC", "VP9", "AV1", "Opus", "MP3"}
    # royalty-free formats are in every build of the engine
    for name in ("VP9", "AV1", "Opus", "MP3"):
        assert declared[name] and decoded[name], name
    # an engine never decodes what it says it cannot play
    for name, ok in decoded.items():
        if ok:
            assert declared[name], name
    text = md.read_text("utf-8")
    assert "| Declares |" in text and "| Decodes (clips played) |" in text
    # no files left in the user's folders: the probe's profiles are private
    assert not (tmp_path / "d").exists() and not (tmp_path / "c").exists()


def test_clips_are_not_packaged():
    """The clips are test data: the PKGBUILD installs ike/ only, and no clip
    lives under ike/."""
    assert not list((ROOT / "ike").rglob("*.mp4")) and not list((ROOT / "ike").rglob("*.m4a"))
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    assert "tests/media" not in pkgbuild
