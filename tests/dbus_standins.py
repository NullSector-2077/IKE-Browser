"""Stand-ins for the desktop services I.K.E. talks to, on a private test bus.

Runs as its own process: ``python3 dbus_standins.py LOGFILE``. It owns
org.kde.JobViewServer (Plasma's download progress), org.kde.kdeconnect (one
paired phone) and org.freedesktop.ScreenSaver, answers like them and writes
every call it receives to LOGFILE as one JSON line, and also the signals that
Plasma's task manager (LauncherEntry) and KRunner (kconfig notify) listen to. Writing "cancel" into
LOGFILE + ".cmd" makes the job view ask for the download to be cancelled.
"""

import json
import os
import sys
import time

from jeepney import DBusAddress, HeaderFields, MatchRule, MessageType, new_method_return, new_signal
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

LOG = sys.argv[1]
NAMES = ("org.kde.JobViewServer", "org.kde.kdeconnect", "org.freedesktop.ScreenSaver")


def log(**kw):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw, default=str) + "\n")


def plain(v):
    """Variants (signature, value) -> value, recursively for dicts."""
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str):
        return plain(v[1])
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v


def main():
    conn = open_dbus_connection("SESSION")
    for n in NAMES:
        conn.send_and_get_reply(message_bus.RequestName(n))
    for iface in ("com.canonical.Unity.LauncherEntry", "org.kde.kconfig.notify"):
        conn.send_and_get_reply(message_bus.AddMatch(MatchRule(type="signal", interface=iface)))
    log(event="ready")
    views = []
    cookie = 100
    while True:
        cmd = LOG + ".cmd"
        if os.path.exists(cmd):
            what = open(cmd).read().strip()
            os.remove(cmd)
            if what == "cancel" and views:
                conn.send(new_signal(DBusAddress(views[-1], interface="org.kde.JobViewV3"),
                                     "cancelRequested"))
                log(event="sent-cancel", path=views[-1])
        try:
            msg = conn.receive(timeout=0.1)
        except TimeoutError:
            continue
        h = msg.header
        f = h.fields
        if h.message_type == MessageType.signal:
            if f.get(HeaderFields.interface) in ("com.canonical.Unity.LauncherEntry", "org.kde.kconfig.notify"):
                log(event="signal", path=f.get(HeaderFields.path), iface=f.get(HeaderFields.interface),
                    member=f.get(HeaderFields.member), body=[plain(x) for x in msg.body])
            continue
        if h.message_type != MessageType.method_call:
            continue
        path, iface, member = f.get(HeaderFields.path), f.get(HeaderFields.interface), f.get(HeaderFields.member)
        log(event="call", path=path, iface=iface, member=member, body=plain(msg.body))
        reply = new_method_return(msg)
        if member == "requestView":
            p = "/org/kde/notificationmanager/jobs/JobView_%d" % (len(views) + 1)
            views.append(p)
            reply = new_method_return(msg, "o", (p,))
        elif member == "deviceNames":
            reply = new_method_return(msg, "a{ss}", ({"abc123": "Pixel"},))
        elif member == "devices":
            reply = new_method_return(msg, "as", (["abc123"],))
        elif member == "Inhibit":
            cookie += 1
            reply = new_method_return(msg, "u", (cookie,))
        if not (h.flags & 1):
            conn.send(reply)
        time.sleep(0)


if __name__ == "__main__":
    main()
