"""A stand-in for the XDG desktop portal's OpenURI, on a private test bus.

Runs as its own process: ``python3 portal_standin.py LOGFILE [old]``. It owns
org.freedesktop.portal.Desktop and answers OpenFile, OpenDirectory and
OpenURI as the portal does (a request handle), writing each call to LOGFILE
as one JSON line: the method, the file the descriptor it received points to
(read from /proc/self/fd, as the portal itself checks it), the link, the
options. "old": a portal from before OpenDirectory (version 2), which does
not know that method.
"""

import json
import os
import sys

from jeepney import HeaderFields, MessageType, new_error, new_method_return
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

LOG = sys.argv[1]
OLD = len(sys.argv) > 2 and sys.argv[2] == "old"


def log(**kw):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw, default=str) + "\n")


def plain(v):
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str):
        return plain(v[1])
    return v


def main():
    conn = open_dbus_connection("SESSION", enable_fds=True)
    conn.send_and_get_reply(message_bus.RequestName("org.freedesktop.portal.Desktop"))
    log(event="ready")
    n = 0
    while True:
        try:
            msg = conn.receive()
        except (OSError, EOFError):
            return                              # the test bus is gone: the test is over
        h = msg.header
        if h.message_type != MessageType.method_call:
            continue
        f = h.fields
        member, iface = f.get(HeaderFields.member), f.get(HeaderFields.interface)
        if iface != "org.freedesktop.portal.OpenURI" or (OLD and member == "OpenDirectory"):
            conn.send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod", "s", ("no such method",)))
            log(event="refused", member=member)
            continue
        entry = {"event": "call", "member": member, "parent": msg.body[0]}
        if member in ("OpenFile", "OpenDirectory"):
            fd = msg.body[1]
            try:
                entry["path"] = os.readlink("/proc/self/fd/%d" % fd.fileno())
            finally:
                fd.close()
        else:
            entry["uri"] = msg.body[1]
        entry["options"] = plain(msg.body[2])
        log(**entry)
        n += 1
        conn.send(new_method_return(msg, "o", ("/org/freedesktop/portal/desktop/request/1_1/ike%d" % n,)))


if __name__ == "__main__":
    main()
