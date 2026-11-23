"""A D-Bus session-bus connection that lives on Qt's event loop.

Messages are built and parsed by jeepney (pure Python, packaged as
``python-jeepney``), which lets I.K.E. use exact D-Bus types such as the
``a(sssida{sv})`` that KRunner expects; QtDBus cannot express those from
Python. The socket is read through a QSocketNotifier, so nothing blocks and no
thread is needed. If jeepney or a session bus is missing, ``connect()`` returns
False and the desktop integration simply stays off.
"""

import array
import os
import socket
from itertools import count

from PyQt6.QtCore import QObject, QSocketNotifier

try:
    from jeepney import (
        DBusAddress,
        HeaderFields,
        MessageType,
        Parser,
        new_error,
        new_method_call,
        new_method_return,
        new_signal,
    )
    from jeepney.bus import get_bus
    from jeepney.io.blocking import prep_socket
    AVAILABLE = True
except Exception:          # not installed: the integration stays off
    AVAILABLE = False
try:                       # file descriptors over the bus (jeepney 0.7 and later)
    from jeepney.fds import FileDescriptor, fds_buf_size
    FDS = True
except Exception:
    FDS = False

DBUS = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")


class BusError(Exception):
    def __init__(self, name, text=""):
        super().__init__(text or name)
        self.name = name


class Bus(QObject):
    """Exports objects, calls methods asynchronously and receives signals.

    fds=True: the connection can pass file descriptors (type "h"), as the
    desktop portal's OpenFile wants (handoff.py, 1.1.24)."""

    def __init__(self, parent=None, fds=False):
        super().__init__(parent)
        self.fds = fds
        self.sock = None
        self.parser = None
        self.serial = count(1)
        self.unique_name = ""
        self._notifier = None
        self._pending = {}           # serial -> (on_reply, on_error)
        self._objects = {}           # path -> handler(msg) -> (signature, body) | None
        self._signals = []           # (sender, path, interface, member, callback)
        self.names = set()

    # --- connection ----------------------------------------------------------
    def connect(self):
        if not AVAILABLE or not os.environ.get("DBUS_SESSION_BUS_ADDRESS") or (self.fds and not FDS):
            return False
        try:
            sock = prep_socket(get_bus("SESSION"), enable_fds=self.fds, timeout=2.0)
            self.sock, self.parser = sock, Parser()
            hello = new_method_call(DBusAddress(DBUS[1], DBUS[0], DBUS[2]), "Hello")
            serial = next(self.serial)
            sock.sendall(hello.serialise(serial=serial))
            sock.settimeout(2.0)
            while True:
                msg = self._read_one_blocking()
                if msg.header.fields.get(HeaderFields.reply_serial) == serial:
                    self.unique_name = msg.body[0]
                    break
        except Exception:
            self.close()
            return False
        sock.setblocking(False)
        self._notifier = QSocketNotifier(sock.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._readable)
        return True

    def _read_one_blocking(self):
        while True:
            msg = self.parser.get_next_message()
            if msg is not None:
                return msg
            data = self.sock.recv(65536)
            if not data:
                raise ConnectionError("bus closed")
            self.parser.add_data(data)

    @property
    def connected(self):
        return self.sock is not None

    def close(self):
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.names.clear()

    def _send(self, msg):
        if self.sock is None:
            return 0
        serial = next(self.serial)
        fds = array.array("i") if self.fds else None
        data = msg.serialise(serial=serial, fds=fds)
        try:
            self.sock.setblocking(True)
            if fds:
                # the descriptors travel with the first bytes (SCM_RIGHTS); the
                # bus has its own copies once sendmsg returns
                sent = self.sock.sendmsg([data], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, fds)])
                if sent < len(data):
                    self.sock.sendall(data[sent:])
            else:
                self.sock.sendall(data)
            self.sock.setblocking(False)
        except OSError:
            self.close()
            return 0
        return serial

    def _readable(self, *_):
        while self.sock is not None:
            got = []
            try:
                if self.fds:
                    data, anc, _flags, _addr = self.sock.recvmsg(65536, fds_buf_size())
                    got = FileDescriptor.from_ancdata(anc)
                else:
                    data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self.close()
                return
            if not data:
                self.close()
                return
            self.parser.add_data(data, fds=got)
        while self.parser is not None:
            try:
                msg = self.parser.get_next_message()
            except Exception:
                self.close()
                return
            if msg is None:
                break
            try:
                self._dispatch(msg)
            except Exception:
                import traceback
                traceback.print_exc()

    # --- incoming ------------------------------------------------------------
    def _dispatch(self, msg):
        h = msg.header
        f = h.fields
        if h.message_type in (MessageType.method_return, MessageType.error):
            cbs = self._pending.pop(f.get(HeaderFields.reply_serial), None)
            if cbs is None:
                return
            on_reply, on_error = cbs
            if h.message_type == MessageType.method_return:
                if on_reply:
                    on_reply(*msg.body)
            elif on_error:
                on_error(BusError(f.get(HeaderFields.error_name, ""), msg.body[0] if msg.body else ""))
            return
        if h.message_type == MessageType.signal:
            # the bus already filtered by sender (the match rules); check the rest
            for _sender, path, iface, member, cb in list(self._signals):
                if ((path is None or f.get(HeaderFields.path) == path)
                        and (iface is None or f.get(HeaderFields.interface) == iface)
                        and (member is None or f.get(HeaderFields.member) == member)):
                    cb(msg)
            return
        if h.message_type != MessageType.method_call:
            return
        path = f.get(HeaderFields.path)
        handler = self._objects.get(path)
        try:
            if handler is None:
                raise BusError("org.freedesktop.DBus.Error.UnknownObject", "No such object")
            result = handler(msg)
            if result is None:
                raise BusError("org.freedesktop.DBus.Error.UnknownMethod",
                               "Unknown method %s.%s" % (f.get(HeaderFields.interface), f.get(HeaderFields.member)))
            sig, body = result
            reply = new_method_return(msg, sig or None, body)
        except BusError as e:
            reply = new_error(msg, e.name, "s", (str(e),))
        except Exception as e:
            reply = new_error(msg, "org.freedesktop.DBus.Error.Failed", "s", (str(e),))
        if not (h.flags & 1):             # NO_REPLY_EXPECTED
            self._send(reply)

    # --- outgoing ------------------------------------------------------------
    def export(self, path, handler):
        self._objects[path] = handler

    def call(self, dest, path, iface, member, sig=None, body=(), on_reply=None, on_error=None):
        msg = new_method_call(DBusAddress(path, dest, iface), member, sig, tuple(body))
        serial = self._send(msg)
        if serial and (on_reply or on_error):
            self._pending[serial] = (on_reply, on_error)
        elif not serial and on_error:
            on_error(BusError("org.freedesktop.DBus.Error.Disconnected", "not connected"))
        return serial

    def emit(self, path, iface, member, sig=None, body=()):
        self._send(new_signal(DBusAddress(path, interface=iface), member, sig, tuple(body)))

    def request_name(self, name, on_done=None):
        def got(code):
            if code in (1, 4):              # primary owner / already owner
                self.names.add(name)
            if on_done:
                on_done(code in (1, 4))
        # flags 4: do not queue
        self.call(*DBUS, "RequestName", "su", (name, 4), got, lambda e: on_done and on_done(False))

    def release_name(self, name):
        if name in self.names:
            self.names.discard(name)
            self.call(*DBUS, "ReleaseName", "s", (name,))

    def on_signal(self, sender, path, iface, member, callback):
        """Receive a signal; sender is a bus name (well-known names are matched loosely)."""
        rule = ",".join("%s='%s'" % kv for kv in (
            ("type", "signal"), ("sender", sender), ("path", path), ("interface", iface), ("member", member))
            if kv[1])
        self.call(*DBUS, "AddMatch", "s", (rule,))
        self._signals.append((sender, path, iface, member, callback))


def introspection(interfaces):
    """Minimal introspection XML: {interface: xml of its members}."""
    parts = ['<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN" '
             '"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">', "<node>"]
    for name, body in interfaces.items():
        parts.append('<interface name="%s">%s</interface>' % (name, body))
    parts.append("</node>")
    return "".join(parts)
