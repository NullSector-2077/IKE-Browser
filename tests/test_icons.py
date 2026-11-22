"""On KDE Plasma every icon of the interface is KDE's own (1.1.22, the
owner's rule): with the desktop's icon theme (Breeze), no icon comes from
I.K.E.'s shipped glyphs, from Qt's own or from another theme.

Every window, menu and Settings page the text-fit test opens is opened with
KDE's theme (QT_QPA_PLATFORMTHEME=kde), and every icon asked for through
ike.icons.themed is checked: it came from the theme, under a name Breeze
itself has. Run where Breeze and plasma-integration are installed (the Arch
Linux job), skipped elsewhere."""

from pathlib import Path

import pytest
from conftest import screen
from test_text_fit import SCREEN, SCRIPTS, STEPS, TESTS

BREEZE_DIRS = [Path("/usr/share/icons/breeze"), Path("/usr/share/icons/breeze-dark")]


def breeze_names():
    names = set()
    for d in BREEZE_DIRS:
        if d.is_dir():
            for f in d.rglob("*"):
                if f.suffix in (".svg", ".png") or f.is_symlink():
                    names.add(f.name.rsplit(".", 1)[0])
    return names


def test_every_icon_is_kdes_own_on_kde(run_ike, tmp_path):
    have = breeze_names()
    if not have or not Path("/usr/lib/qt6/plugins/platformthemes/KDEPlasmaPlatformTheme6.so").exists():
        pytest.skip("KDE's Breeze icons and platform theme are not installed here")
    script = (STEPS.replace("TESTS", repr(str(TESTS))).replace("LANGS", repr(["en"]))
              .replace("SCRIPTS", repr(SCRIPTS))
              .replace('    out["problems"] = problems\n',
                       '    out["problems"] = problems\n'
                       '    from ike import icons\n'
                       '    from PyQt6.QtGui import QIcon\n'
                       '    out["theme"] = QIcon.themeName()\n'
                       '    out["icons"] = [[list(k), v[0], v[1]] for k, v in icons.seen.items()]\n'))
    env = dict(screen(tmp_path, *SCREEN), QT_QPA_PLATFORMTHEME="kde")
    out = run_ike(script, env=env, timeout=600)
    if not str(out.get("theme", "")).startswith("breeze"):
        pytest.skip("KDE's theme did not load here (icon theme %r)" % out.get("theme"))
    assert len(out["icons"]) > 40, len(out["icons"])
    wrong = [[names, source, used] for names, source, used in out["icons"]
             if source != "theme" or used not in have]
    report = "\n".join("%s -> %s %s" % (", ".join(n), s, u) for n, s, u in wrong)
    assert not wrong, "%d icons not from KDE's theme:\n%s" % (len(wrong), report)
