"""The password vault locks itself (ike/vaultlock.py, Unreleased).

After the chosen minutes without a key, click, wheel turn or touch in I.K.E.
(15 by default, "Never" keeps the old behaviour), and when the desktop locks
the screen or the computer goes to sleep. Nothing runs while it is locked, a
bus message can only lock it, and the Passwords window offers the choices.
"""

STEPS = r'''
import time
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

def steps(ike, qapp, out):
    yield 300
    pm = ike.passwords
    lk = pm.locker
    out["idle_before"] = [lk._watching, lk._timer.isActive()]
    pm.vault.create("test master")
    pm.locker.opened()
    out["open"] = [pm.vault.unlocked, lk._watching, lk._timer.isActive(), lk._timer.interval()]
    t0 = lk.last_input
    out["early"] = [lk.check(t0 + 14 * 60), pm.vault.unlocked]
    # a real key in the window counts as use
    win = ike.windows[0]
    win.activateWindow()
    lk.last_input = t0 - 3600
    QTest.keyClick(win.urlbar, Qt.Key.Key_A)
    yield 50
    out["key_counts"] = lk.last_input > t0 - 60
    out["late"] = [lk.check(lk.last_input + 15 * 60 + 1), pm.vault.unlocked, lk._watching,
                   lk._timer.isActive(), pm.locked_because]
    # "Never": nothing is watched, nothing locks by time
    ike.config["pw_lock_minutes"] = 0
    pm.vault.unlock("test master")
    pm.locker.opened()
    out["never"] = [lk._watching, lk._timer.isActive(), lk.check(time.monotonic() + 10 ** 6),
                    pm.vault.unlocked]
    # a value from an edited settings file falls back to the default
    ike.config["pw_lock_minutes"] = "eleven"
    from ike.vaultlock import minutes_of
    out["odd"] = minutes_of(ike.config)
    ike.config["pw_lock_minutes"] = 15
    pm.locker.changed()
    out["changed"] = [lk._watching, lk._timer.isActive()]
    # the screen locked: through the session bus when there is one
    out["bus_links"] = lk.bus_links
    out["after_false"] = None
    if BUS:
        from PyQt6.QtCore import QProcess
        def emit(value):
            p = QProcess()
            p.start("gdbus", ["emit", "--session", "--object-path", "/ScreenSaver", "--signal",
                              "org.freedesktop.ScreenSaver.ActiveChanged", value])
            return p
        p = emit("false")
        for _ in range(30):
            yield 100
        out["after_false"] = pm.vault.unlocked
        p = emit("true")
        for _ in range(30):
            yield 100
            if not pm.vault.unlocked:
                break
        out["after_true"] = [pm.vault.unlocked, pm.locked_because, lk._watching]
    else:
        lk.screen_locked()
        out["after_true"] = [pm.vault.unlocked, pm.locked_because, lk._watching]
    # the switch off: the screen locking leaves the vault open
    ike.config["pw_lock_screen"] = False
    pm.vault.unlock("test master")
    pm.locker.opened()
    lk.screen_locked()
    out["switch_off"] = pm.vault.unlocked
    ike.config["pw_lock_screen"] = True
    # the Passwords window: the choices, and a lock closes it
    from ike.passwords import PasswordsDialog
    dlg = ike._show("passwords", lambda: PasswordsDialog(ike, win))
    yield 100
    out["choices"] = [dlg.lock_after.itemData(i) for i in range(dlg.lock_after.count())]
    out["current"] = dlg.lock_after.currentData()
    out["screen_switch"] = dlg.lock_screen.isChecked()
    dlg.lock_after.setCurrentIndex(dlg.lock_after.findData(5))
    out["saved"] = ike.config["pw_lock_minutes"]
    out["dlg_visible"] = dlg.isVisible()
    lk.screen_locked()
    yield 100
    out["dlg_after"] = dlg.isVisible()
    out["unlocked_end"] = pm.vault.unlocked
'''


def _run(run_ike, bus, env):
    return run_ike(("BUS = %r\n" % bus) + STEPS, env=env, timeout=120)


def test_vault_locks_itself(run_ike):
    out = _run(run_ike, False, None)
    _common(out)


def test_vault_locks_with_the_screen_over_the_bus(run_ike, desktop_bus):
    address, _log, _f = desktop_bus
    out = _run(run_ike, True, {"DBUS_SESSION_BUS_ADDRESS": address})
    _common(out)
    assert out["bus_links"] >= 3
    assert out["after_false"] is True                      # "not active" changes nothing


def _common(out):
    assert out["idle_before"] == [False, False]             # nothing runs while locked
    assert out["open"] == [True, True, True, 60_000]
    assert out["early"] == [False, True]
    assert out["key_counts"]
    assert out["late"] == [True, False, False, False, "idle"]
    assert out["never"] == [False, False, False, True]
    assert out["odd"] == 15
    assert out["changed"] == [True, True]
    assert out["after_true"] == [False, "screen", False]
    assert out["switch_off"] is True
    assert out["choices"] == [0, 5, 15, 30, 60] and out["current"] == 15
    assert out["screen_switch"] is True
    assert out["saved"] == 5
    assert out["dlg_visible"] and not out["dlg_after"] and not out["unlocked_end"]
