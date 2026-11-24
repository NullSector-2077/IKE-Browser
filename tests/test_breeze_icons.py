"""1.1.24: KDE's Breeze icons shipped with I.K.E. (the owner's request).

The set "Breeze (KDE)" (ike/resources/icons/sets/breeze) is built by
tools/build-breeze-icons.py from a release of KDE's breeze-icons: only the
icons I.K.E. uses, one SVG per name, drawn in the interface's text colour like
the other shipped sets. So I.K.E. has KDE's icons even where breeze-icons is not
installed (it is not a dependency of the package). Here:

- the set is offered, every icon loads and draws, and it has an icon for every
  name the interface asks for and every name the other sets have;
- the new tab page's Settings icon (icons.theme_svg) is Breeze's whatever the
  icon theme in use: the installed Breeze theme, else this set (before the
  theme in use, never Lucide);
- choosing it in Settings switches the interface's icons to it;
- its licence (LGPL-3.0-or-later: Breeze's notice and the complete LGPL v3) and
  its record (release tag, commit, the Breeze file of each icon) are there;
- the builder, on a small stand-in upstream: only one-colour icons, symbolic
  links resolved, aliases, nothing but a plain drawing, the same output twice;
- the daily check (tools/check-components.py, the manifest's "breeze-icons")
  follows a new release by itself, and refuses one that lost an icon.

Offline: the upstream checkouts are stand-ins made here.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "ike" / "resources" / "icons" / "sets" / "breeze"
RECORD = SET / "breeze-icons.json"
# sha256 of https://www.gnu.org/licenses/lgpl-3.0.txt (7651 bytes; the same bytes as Debian's
# /usr/share/common-licenses/LGPL-3)
LGPL3_SHA256 = "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_breeze", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = load("build-breeze-icons")


def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def record():
    return json.loads(RECORD.read_text("utf-8"))


# --- the set --------------------------------------------------------------------------------------

def test_the_set_is_offered_and_every_icon_draws_in_the_text_colour():
    app = qapp()                                                       # noqa: F841 (kept alive)
    from PyQt6.QtCore import QByteArray, QSize
    from PyQt6.QtGui import QGuiApplication, QPalette
    from PyQt6.QtSvg import QSvgRenderer

    from ike import icons
    assert ("breeze", "Breeze (KDE)") in icons.SETS
    files = sorted(SET.glob("*.svg"))
    assert len(files) >= 90, len(files)
    # small: well under 1 MB with its record (about 85 KB at 6.32.0)
    size = sum(p.stat().st_size for p in SET.iterdir())
    assert size < 256 * 1024, size
    colour = QGuiApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText)
    for path in files:
        text = path.read_text("utf-8")
        assert text.startswith("<svg") and "currentColor" in text, path.name
        assert "<style" not in text and "<?xml" not in text, path.name
        assert not builder.UNSAFE.search(text), path.name             # a plain drawing only
        assert not builder.COLOUR.search(text), path.name             # no colour of its own
        assert QSvgRenderer(QByteArray(text.encode())).isValid(), path.name
        # loaded lazily, like the other sets, and drawn in the palette's text colour
        ic = icons.bundled(path.stem, "breeze")
        assert not ic.isNull(), path.name
        img = ic.pixmap(QSize(22, 22)).toImage()
        drawn = [img.pixelColor(x, y) for x in range(22) for y in range(22) if img.pixelColor(x, y).alpha() > 200]
        assert drawn, path.name
        assert all(abs(c.red() - colour.red()) < 8 and abs(c.green() - colour.green()) < 8
                   and abs(c.blue() - colour.blue()) < 8 for c in drawn), path.name


def test_every_name_the_interface_asks_for_is_in_the_set():
    have = {p.stem for p in SET.glob("*.svg")}
    rec = record()
    assert set(rec["icons"]) == have
    # the record follows the code: a name added to the interface needs the builder run again
    assert sorted(have | set(rec["not_in_breeze"])) == builder.wanted(ROOT), \
        "the set is out of date: run python3 tools/build-breeze-icons.py --src <breeze-icons checkout>"
    requests = builder.requests(ROOT)
    assert len(requests) > 50
    missing = ["%s: %s" % (f, " / ".join(names)) for f, names in requests if not set(names) & have]
    assert not missing, "requests with no Breeze icon:\n" + "\n".join(missing)
    for folder in builder.OTHER_SETS:
        names = {p.stem for p in (ROOT / folder).glob("*.svg")}
        assert names and names <= have, (folder, sorted(names - have))
    # the reading of the code finds what the interface really asks for
    flat = {n for _f, names in requests for n in names}
    assert {"configure", "go-home", "tab-new", "view-refresh", "audio-volume-muted", "kdeconnect"} <= flat


def test_the_record_the_manifest_and_the_licence():
    rec = record()
    assert rec["source"] == "https://github.com/KDE/breeze-icons" and rec["licence"] == "LGPL-3.0-or-later"
    assert rec["tag"] == "v" + rec["version"] and len(rec["commit"]) == 40 and int(rec["commit"], 16) >= 0
    assert rec["builder"] == "tools/build-breeze-icons.py" and rec["licence_file"] == "licenses/LICENSE.breeze-icons"
    for name, where in rec["icons"].items():           # the Breeze file of each icon
        for part in where.split(" -> "):
            context, size, file = part.split("/")
            assert context in builder.CONTEXTS and size.isdigit() and file.endswith(".svg"), (name, where)
    manifest = load("component-manifest")
    entry = manifest.read(ROOT)["components"]["breeze-icons"]
    assert entry["upstream"] == {"git": "https://github.com/KDE/breeze-icons", "tag": "v*"}
    assert entry["build"] == "tools/build-breeze-icons.py" and entry["build"] in manifest.BUILDERS
    assert entry["licence"] == "licenses/LICENSE.breeze-icons" and entry["kinds"] == ["integrated"]
    assert set(manifest.DEFAULT_TESTS) <= set(entry["tests"])
    assert sorted(entry["files"]) == sorted(str(p.relative_to(ROOT)) for p in SET.iterdir()), \
        "components.json lists exactly the files of the set"
    lgpl = (ROOT / builder.LGPL_TEXT).read_bytes()
    assert hashlib.sha256(lgpl).hexdigest() == LGPL3_SHA256
    text = (ROOT / "licenses" / "LICENSE.breeze-icons").read_text("utf-8")
    assert text.endswith(lgpl.decode("utf-8"))
    assert "--- COPYING-ICONS ---" in text and "Copyright (C) 2014 Uri Herrera" in text
    assert "either\n    version 3 of the License, or (at your option) any later version." in text
    assert "tag %s, commit %s (%s)" % (rec["tag"], rec["commit"], rec["date"]) in text
    assert "is the file LICENSE next to this one" in text
    for doc in ("COPYRIGHT", "docs/THIRD-PARTY.md"):
        assert "LICENSE.breeze-icons" in (ROOT / doc).read_text("utf-8"), doc


# --- where it is used -------------------------------------------------------------------------------

def test_the_new_tab_settings_icon_falls_back_to_the_shipped_breeze(tmp_path):
    qapp()
    from PyQt6.QtGui import QIcon

    from ike import icons
    paths, name = QIcon.themeSearchPaths(), QIcon.themeName()
    kept = icons._set, icons._system_theme
    icons._set, icons._system_theme = None, None          # the default choice ("system")
    try:
        # no icon theme at all (a desktop without breeze-icons): the shipped Breeze icon
        QIcon.setThemeSearchPaths([str(tmp_path / "none")])
        QIcon.setThemeName("nothing-here")
        svg = icons.theme_svg("configure")
        assert svg and svg == icons._plain_svg(SET / "configure.svg")
        assert svg.startswith("<svg") and "currentColor" in svg and "<style" not in svg
        assert icons.theme_svg("no-such-icon-anywhere") == ""
        # another icon theme in use (Papirus, Adwaita...) and no Breeze installed: the shipped Breeze
        # icon still wins (the owner's choice: the new tab page's Settings icon is always KDE's)
        other = tmp_path / "themes" / "papirus" / "actions" / "22"
        other.mkdir(parents=True)
        for icon in ("configure", "only-in-papirus"):
            (other / (icon + ".svg")).write_text('<svg xmlns="http://www.w3.org/2000/svg"><path id="papirus" '
                                                 'd="M0 0h1v1z"/></svg>')
        QIcon.setThemeSearchPaths([str(tmp_path / "themes")])
        QIcon.setThemeName("papirus")
        assert icons.theme_svg("configure") == icons._plain_svg(SET / "configure.svg")
        assert 'id="papirus"' in icons.theme_svg("only-in-papirus")       # what Breeze has not: the theme in use
        # the installed Breeze themes come first of all (breeze, then breeze-dark)
        dark = tmp_path / "themes" / "breeze-dark" / "actions" / "22"
        dark.mkdir(parents=True)
        (dark / "configure.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path id="dark" '
                                            'd="M0 0h1v1z"/></svg>')
        assert 'id="dark"' in icons.theme_svg("configure")
        own = tmp_path / "themes" / "breeze" / "actions" / "22"
        own.mkdir(parents=True)
        (own / "configure.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path id="mine" '
                                           'd="M0 0h1v1z"/></svg>')
        assert 'id="mine"' in icons.theme_svg("configure")
        (dark / "configure.svg").unlink()
        # another icon theme chosen in the Settings (#138): that theme first
        icons._system_theme = "breeze"
        assert 'id="papirus"' in icons.theme_svg("configure")
        icons._system_theme = None
        # a set shipped with I.K.E. chosen: its own drawing; "Breeze (KDE)" is the shipped Breeze,
        # even where the Breeze theme is installed
        icons._set = "breeze"
        assert icons.theme_svg("configure") == icons._plain_svg(SET / "configure.svg")
        icons._set = "lucide"
        assert icons.theme_svg("configure") == icons._plain_svg(SET.parent / "lucide" / "configure.svg")
        icons._set = None
        # and a file that is more than a drawing is never put into the page
        (own / "configure.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>')
        assert icons.theme_svg("configure") == icons._plain_svg(SET / "configure.svg")
    finally:
        QIcon.setThemeSearchPaths(paths)
        QIcon.setThemeName(name)
        icons._set, icons._system_theme = kept


SWITCH = r"""
def steps(ike, qapp, out):
    from PyQt6.QtGui import QIcon
    from ike import icons
    yield 300
    # the default choice ("system") on a desktop with no icon theme at all (no breeze-icons): the new
    # tab page's Settings button is still KDE's Breeze, the one shipped with I.K.E.
    out["choice"] = ike.config["icon_theme"]
    QIcon.setThemeSearchPaths([])
    out["newtab_default"] = ike.shields._newtab_buttons()
    win = ike.windows[0]
    dlg = win.open_settings("appearance")
    yield 200
    box = dlg.icon_theme
    out["offered"] = [box.itemData(i) for i in range(box.count())]
    out["label"] = box.itemText(box.findData("set:breeze"))
    box.setCurrentIndex(box.findData("set:breeze"))
    dlg.apply()
    yield 200
    dlg.close()
    out["setting"] = ike.config["icon_theme"]
    out["set"] = icons._set
    icons.seen.clear()
    icons._found.clear()
    for names in (("configure",), ("go-home",), ("view-refresh",), ("picture-in-picture",)):
        ic = icons.themed(names)
        out.setdefault("icons", []).append([list(names), list(icons.seen[names]), not ic.isNull()])
    # the new tab page's Settings button, on a desktop with no icon theme
    QIcon.setThemeSearchPaths([])
    QIcon.setThemeName("nothing-here")
    out["newtab"] = ike.shields._newtab_buttons()
    out["breeze_configure"] = icons._plain_svg(icons._SETS_DIR / "breeze" / "configure.svg")
    out["lucide_configure"] = (icons._SETS_DIR / "lucide" / "configure.svg").read_text("utf-8")
"""


def test_choosing_breeze_in_settings_switches_the_icons(run_ike):
    out = run_ike(SWITCH, timeout=120)
    assert "set:breeze" in out["offered"] and "set:lucide" in out["offered"]
    assert out["label"].startswith("Breeze (KDE)")
    assert out["setting"] == "set:breeze" and out["set"] == "breeze"
    assert out["icons"] == [[["configure"], ["set", "configure"], True], [["go-home"], ["set", "go-home"], True],
                            [["view-refresh"], ["set", "view-refresh"], True],
                            [["picture-in-picture"], ["set", "picture-in-picture"], True]]
    # Breeze wins over Lucide on the new tab page even without breeze-icons installed: with the
    # default choice, and with the set "Breeze (KDE)" chosen
    assert out["choice"] == "system"
    for page in (out["newtab_default"], out["newtab"]):
        assert out["breeze_configure"] and out["breeze_configure"] in page
        assert out["lucide_configure"].strip() not in page


# --- the builder, on a stand-in upstream --------------------------------------------------------------

BREEZE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22">
  <defs id="defs3051">
    <style type="text/css" id="current-color-scheme">
      .ColorScheme-Text {
        color:#232629;
      }
      </style>
  </defs>
 <!-- %s -->
 <path style="fill:currentColor;fill-opacity:1;stroke:none" d="M 3 3 L 19 3 L 19 19 Z" class="ColorScheme-Text"/>
</svg>
"""
COLOURED = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22"><path fill="#3daee9" d="M0 0h22v22z"/></svg>\n'
NOTICE = """The Breeze Icon Theme in icons/

    Copyright (C) 2014 Uri Herrera <uri_herrera@nitrux.in> and others

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 3 of the License, or (at your option) any later version.
"""


def stand_in(path, names, marker="v1", tag="v6.99.0"):
    """A breeze-icons checkout with these names, one per line of NAMES, in actions/22, as a git
    repository tagged `tag`."""
    a22 = path / "icons" / "actions" / "22"
    a22.mkdir(parents=True, exist_ok=True)
    for name in names:
        (a22 / (name + ".svg")).write_text(BREEZE_SVG % ("%s %s" % (name, marker)), "utf-8")
    (path / "COPYING-ICONS").write_text(NOTICE, "utf-8")
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    if not (path / ".git").exists():
        subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", marker], check=True)
    subprocess.run(git + ["tag", "-f", tag], check=True, capture_output=True)
    return path


needs_git = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


def test_the_builder_takes_only_plain_one_colour_drawings(tmp_path):
    src = tmp_path / "breeze"
    a22, a16 = src / "icons" / "actions" / "22", src / "icons" / "actions" / "16"
    a22.mkdir(parents=True)
    a16.mkdir(parents=True)
    (src / "COPYING-ICONS").write_text(NOTICE, "utf-8")
    (a22 / "configure.svg").write_text(BREEZE_SVG % "configure", "utf-8")
    (a22 / "go-home.svg").write_text(COLOURED, "utf-8")                      # in colour at 22: not taken
    (a16 / "go-home.svg").write_text(BREEZE_SVG % "home 16", "utf-8")        # one colour at 16: taken
    (a22 / "go-previous.svg").write_text(BREEZE_SVG % "previous", "utf-8")
    (a22 / "go-next.svg").symlink_to("go-previous.svg")                     # a link, resolved
    (a22 / "window-minimize-pip.svg").write_text(BREEZE_SVG % "pip", "utf-8")  # an alias
    (a22 / "tab-new-symbolic.svg").write_text(BREEZE_SVG % "tab", "utf-8")     # the -symbolic form
    kw = {"tag": "v6.99.0", "commit": "a" * 40, "date": "2026-11-23"}
    files = builder.build(src, ROOT, **kw)
    rec = json.loads(files[builder.SET_DIR + "/" + builder.RECORD])
    assert rec["icons"] == {"configure": "actions/22/configure.svg", "go-home": "actions/16/go-home.svg",
                            "go-next": "actions/22/go-next.svg -> actions/22/go-previous.svg",
                            "go-previous": "actions/22/go-previous.svg",
                            "picture-in-picture": "actions/22/window-minimize-pip.svg",
                            "tab-new": "actions/22/tab-new-symbolic.svg"}
    assert rec["version"] == "6.99.0" and "view-refresh" in rec["not_in_breeze"]
    configure = files[builder.SET_DIR + "/configure.svg"]
    assert configure.startswith('<svg fill="currentColor" xmlns=') and "<style" not in configure
    assert "<!--" not in configure and "DOCTYPE" not in configure and "<defs" not in configure
    assert 'd="M 3 3 L 19 3 L 19 19 Z"' in configure                          # the drawing itself, unchanged
    assert files == builder.build(src, ROOT, **kw)                            # deterministic
    assert files[builder.LICENCE].endswith((ROOT / builder.LGPL_TEXT).read_text("utf-8"))
    # written: the set's old icons it no longer has are removed
    out = tmp_path / "out"
    (out / builder.SET_DIR).mkdir(parents=True)
    (out / builder.SET_DIR / "old-name.svg").write_text("<svg/>")
    builder.write(files, out)
    assert sorted(p.name for p in (out / builder.SET_DIR).iterdir()) == sorted(
        [n + ".svg" for n in rec["icons"]] + [builder.RECORD])
    # anything but a plain drawing stops the build
    for bad in ('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"/>',
                '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x.test/a.png"/></svg>',
                '<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>'):
        (a22 / "configure.svg").write_text(bad, "utf-8")
        with pytest.raises(builder.Refused):
            builder.build(src, ROOT, **kw)
    (a22 / "configure.svg").write_text(BREEZE_SVG % "configure", "utf-8")
    # a link out of the checkout, a licence that is no longer the LGPL 3, no release tag
    outside = tmp_path / "outside.svg"
    outside.write_text(BREEZE_SVG % "outside", "utf-8")
    (a22 / "go-up.svg").symlink_to(outside)
    with pytest.raises(builder.Refused, match="outside the checkout"):
        builder.build(src, ROOT, **kw)
    (a22 / "go-up.svg").unlink()
    with pytest.raises(builder.Refused, match="release tag"):
        builder.build(src, ROOT, **dict(kw, tag="master"))
    (src / "COPYING-ICONS").write_text("All rights reserved.\n", "utf-8")
    with pytest.raises(builder.Refused, match="LGPL version 3"):
        builder.build(src, ROOT, **kw)


# --- AUTOMAT: the daily check follows new releases by itself ------------------------------------------

@pytest.fixture
def repo(tmp_path):
    """The parts of the repository the check reads and writes."""
    root = tmp_path / "repo"
    for path in sorted((ROOT / "ike").rglob("*.py")):
        rel = path.relative_to(ROOT)
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, root / rel)
    for folder in builder.OTHER_SETS + (builder.SET_DIR,):
        shutil.copytree(ROOT / folder, root / folder)
    for rel in ("components.json", "tools/build-breeze-icons.py", builder.LGPL_TEXT, builder.LICENCE):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    return root


def upstream_like_the_set(path, tag, change=None, drop=()):
    """A stand-in release with every icon the set has (as the set has it), `change` drawn differently."""
    names = [n for n in record()["icons"] if n not in drop]
    a22 = path / "icons" / "actions" / "22"
    a22.mkdir(parents=True, exist_ok=True)
    for name in names:
        text = (SET / (name + ".svg")).read_text("utf-8")
        if name == change:
            text = text.replace("<svg ", '<svg data-changed="1" ', 1)
        (a22 / (name + ".svg")).write_text(text, "utf-8")
    for old in a22.glob("*.svg"):
        if old.stem not in names:
            old.unlink()
    (path / "COPYING-ICONS").write_text((ROOT / "licenses" / "LICENSE.breeze-icons").read_text("utf-8").split(
        "--- COPYING-ICONS ---\n\n", 1)[1].split("\n\n--- GNU Lesser", 1)[0] + "\n", "utf-8")
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    if not (path / ".git").exists():
        subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", tag], check=True)
    subprocess.run(git + ["tag", "-f", tag], check=True, capture_output=True)
    return path


@needs_git
def test_the_daily_check_follows_a_new_release_and_refuses_a_lost_icon(repo, tmp_path):
    components = load("check-components")
    candidates = load("update-candidates")
    current = record()["version"]
    assert components.family_of("breeze-icons", ROOT) == "breeze-icons"
    spec = candidates.spec("breeze-icons", ROOT)
    assert spec["builder"] == "tools/build-breeze-icons.py" and spec["kinds"] == ("integrated",) and spec["ships"]
    assert candidates.commit_problem("breeze-icons", "update: breeze-icons 6.32.0 -> 6.99.0 (no AI)", [
        "ike/resources/icons/sets/breeze/configure.svg", "ike/resources/icons/sets/breeze/breeze-icons.json",
        "licenses/LICENSE.breeze-icons", "CHANGELOG.md"]) == ""
    assert candidates.commit_problem("breeze-icons", "update: breeze-icons 6.32.0 -> 6.99.0 (no AI)",
                                     ["ike/icons.py"])
    # no newer tag upstream: nothing to do, nothing cloned
    work = tmp_path / "w"
    res = components.check_all(repo, work=work, only="breeze-icons",
                               tags=lambda url, timeout=120: ["v" + current, "v6.0.0", "v7.0.0-rc1"])
    assert [(r["id"], r["update"], r["error"], r["refused"]) for r in res] == [("breeze-icons", False, "", None)]
    assert not (work / "breeze-icons" / "breeze-icons-src").exists()
    # a newer release with the same icons: not an update (a new tag alone does not count)
    tags = (lambda url, timeout=120: ["v" + current, "v6.99.0"])
    checkout = work / "breeze-icons" / "breeze-icons-src"
    upstream_like_the_set(checkout, "v6.99.0")
    res = components.check_all(repo, work=work, only="breeze-icons", tags=tags)
    assert res[0]["error"] == "" and res[0]["update"] is False and res[0]["latest"].startswith("6.99.0 (")
    # one icon drawn differently: an update, applied by itself on its candidate
    upstream_like_the_set(checkout, "v6.99.0", change="configure")
    res = components.check_all(repo, work=work, only="breeze-icons", tags=tags)
    assert res[0]["update"] is True and res[0]["note"] == "1 changed, 0 new, 0 removed", res[0]
    cand = components.apply_candidate(repo, res, "breeze-icons")
    assert cand["to"].startswith("6.99.0")
    done = json.loads((repo / builder.SET_DIR / builder.RECORD).read_text())
    assert done["version"] == "6.99.0" and 'data-changed="1"' in (repo / builder.SET_DIR / "configure.svg").read_text()
    assert "tag v6.99.0, commit %s" % done["commit"] in (repo / builder.LICENCE).read_text()
    plan = candidates.plan({"candidates": components.candidates_of(res)}, {})
    assert [(r["id"], r["action"], r["branch"]) for r in plan] == [
        ("breeze-icons", "make", "automation/update/breeze-icons")]
    # a release that lost an icon the set has: refused, the set stays as it is, and no AI path for it
    before = {p.name: p.read_text() for p in (repo / builder.SET_DIR).iterdir()}
    upstream_like_the_set(checkout, "v6.100.0", drop=("configure",))
    res = components.check_all(repo, work=work, only="breeze-icons",
                               tags=lambda url, timeout=120: ["v6.99.0", "v6.100.0"])
    assert res[0]["refused"] and not res[0]["update"] and not res[0]["error"]
    assert "configure" in res[0]["refused"]["reason"] and "ALIASES" in res[0]["refused"]["step"]
    with pytest.raises(LookupError):
        components.apply_candidate(repo, res, "breeze-icons")
    assert {p.name: p.read_text() for p in (repo / builder.SET_DIR).iterdir()} == before
    plan = candidates.plan({"candidates": components.candidates_of(res)}, {})
    assert [(r["id"], r["action"]) for r in plan] == [("breeze-icons", "skip")]
    assert "no patches an AI may re-anchor" in plan[0]["reason"]
    # an upstream that cannot be read is tried again tomorrow
    def unreachable(url, timeout=120):
        raise OSError("no network")
    res = components.check_all(repo, work=tmp_path / "w2", only="breeze-icons", tags=unreachable)
    assert "source unreachable" in res[0]["error"]


def test_the_inventory_lists_it_with_its_own_candidate():
    inventory = load("inventory")
    recs = [r for r in inventory.inventory(ROOT, offline=True)["components"] if r.get("candidate") == "breeze-icons"]
    assert len(recs) == 1 and recs[0]["kind"] == "integrated"
    assert recs[0]["installed"].startswith(record()["version"] + " (")
    assert inventory.update_path(recs[0]) == "candidate automation/update/breeze-icons"
    # every file of the set must be declared (the inventory guard)
    assert inventory.looks_external(ROOT, "ike/resources/icons/sets/breeze/extra.svg")
    assert not inventory.undeclared_files(ROOT, [str(p.relative_to(ROOT)) for p in SET.iterdir()])
