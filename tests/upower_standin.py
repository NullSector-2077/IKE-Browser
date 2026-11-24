"""A stand-in for UPower on a private test bus (tests/test_privacy_124.py).

Runs as its own process: ``python3 upower_standin.py STATEFILE on|off``. It
owns org.freedesktop.UPower on the bus of DBUS_SESSION_BUS_ADDRESS (the test
hands the same address to I.K.E. as its system bus), answers Get and GetAll
for OnBattery and, when "on" or "off" is written into STATEFILE + ".cmd",
changes it and sends PropertiesChanged, as UPower does when the computer is
unplugged or plugged in. Every call it receives is written to STATEFILE.
"""

import json
import os
import sys

from jeepney import DBusAddress, HeaderFields, MessageType, new_method_return, new_signal
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

LOG = sys.argv[1]
IFACE = "org.freedesktop.UPower"
PATH = "/org/freedesktop/UPower"
PROPS = "org.freedesktop.DBus.Properties"


def log(**kw):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


def main():
    on = sys.argv[2] == "on"
    conn = open_dbus_connection("SESSION")
    conn.send_and_get_reply(message_bus.RequestName(IFACE))
    log(event="ready")
    while True:
        cmd = LOG + ".cmd"
        if os.path.exists(cmd):
            what = open(cmd).read().strip()
            os.remove(cmd)
            on = what == "on"
            conn.send(new_signal(DBusAddress(PATH, interface=PROPS), "PropertiesChanged", "sa{sv}as",
                                 (IFACE, {"OnBattery": ("b", on)}, [])))
            log(event="changed", on=on)
        try:
            msg = conn.receive(timeout=0.1)
        except TimeoutError:
            continue
        h = msg.header
        if h.message_type != MessageType.method_call:
            continue
        member = h.fields.get(HeaderFields.member)
        log(event="call", member=member, body=[str(x) for x in msg.body])
        if member == "Get":
            reply = new_method_return(msg, "v", (("b", on),))
        elif member == "GetAll":
            reply = new_method_return(msg, "a{sv}", ({"OnBattery": ("b", on)},))
        else:
            reply = new_method_return(msg)
        if not (h.flags & 1):
            conn.send(reply)


if __name__ == "__main__":
    main()
