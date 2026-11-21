"""DNS over HTTPS for I.K.E.'s own requests (review of 1.1.19, M3).

The engine resolves the pages' names through the provider chosen in Settings
(Privacy, "Encrypted DNS"). I.K.E.'s own requests did not: the checks of the
home network, the style sheets dark mode fetches for a page, the requests of
user scripts, the sites' icons, updates and filter lists were looked up by
the system's resolver, in clear, and told it which sites were open.

With encrypted DNS on, those names are asked of the same provider (RFC 8484,
the DNS message over an https GET), and the connection goes to the address it
gave. Only the provider's own name is looked up by the system, as the engine
does too. A name the provider does not answer is not looked up in clear: the
request fails, as a page's would.
"""

import base64
import ipaddress
import os
import socket
import struct
import threading
import time
import urllib.request

TEMPLATE = [None]           # the provider's address, while encrypted DNS is on
_CACHE = {}                 # name -> (until, [addresses])
_LOCK = threading.Lock()
_A, _AAAA = 1, 28


def configure(template):
    """Called when the engine's DNS mode is set: the same provider, or None."""
    test = os.environ.get("IKE_TEST_DOH")        # the tests' own provider (plain http, local)
    TEMPLATE[0] = test or template or None
    with _LOCK:
        _CACHE.clear()


def active():
    return TEMPLATE[0] is not None


def _question(name, qtype):
    labels = name.encode("idna").split(b".")
    if any(not 0 < len(p) < 64 for p in labels):
        raise OSError("not a host name: %s" % name)
    return (struct.pack(">HHHHHH", 0, 0x0100, 1, 0, 0, 0)
            + b"".join(bytes([len(p)]) + p for p in labels) + b"\0" + struct.pack(">HH", qtype, 1))


def _skip_name(data, i):
    while True:
        if i >= len(data):
            raise ValueError("short answer")
        n = data[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:
            return i + 2                  # a pointer ends the name
        i += 1 + n


def parse(data, qtype):
    """[(address, ttl)] of type `qtype` in a DNS answer."""
    if len(data) < 12:
        raise ValueError("short answer")
    _id, flags, qd, an, _ns, _ar = struct.unpack(">HHHHHH", data[:12])
    if flags & 0x000F not in (0, 3):       # NOERROR, or NXDOMAIN (no address)
        raise ValueError("the DNS provider answered with an error (%d)" % (flags & 0xF))
    i = 12
    for _ in range(qd):
        i = _skip_name(data, i) + 4
    out = []
    for _ in range(an):
        i = _skip_name(data, i)
        rtype, _cls, ttl, size = struct.unpack(">HHIH", data[i:i + 10])
        i += 10
        rdata = data[i:i + size]
        i += size
        if rtype == qtype == _A and size == 4:
            out.append((socket.inet_ntop(socket.AF_INET, rdata), ttl))
        elif rtype == qtype == _AAAA and size == 16:
            out.append((socket.inet_ntop(socket.AF_INET6, rdata), ttl))
    return out


def _ask(name, qtype):
    from .osinfo import browser_user_agent
    template = TEMPLATE[0]
    query = base64.urlsafe_b64encode(_question(name, qtype)).rstrip(b"=").decode("ascii")
    url = template + ("&" if "?" in template else "?") + "dns=" + query
    req = urllib.request.Request(url, headers={"Accept": "application/dns-message",
                                               "User-Agent": browser_user_agent()})
    with urllib.request.urlopen(req, timeout=10) as r:          # the provider's name: the system's
        return parse(r.read(65536), qtype)


def addresses(name):
    """The addresses of `name` from the provider (IPv4 first), or OSError."""
    name = (name or "").lower().rstrip(".")
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(name)
    if hit and hit[0] > now:
        return list(hit[1])
    found = []
    for qtype in (_A, _AAAA):
        try:
            found += _ask(name, qtype)
        except (OSError, ValueError) as exc:
            if qtype == _A:
                raise OSError("%s: encrypted DNS: %s" % (name, exc)) from None
    if not found:
        raise OSError("%s: no address (encrypted DNS)" % name)
    ttl = max(30, min(3600, min(t for _, t in found)))
    result = [a for a, _ in found]
    with _LOCK:
        _CACHE[name] = (now + ttl, result)
    return result


def lookup(name):
    """The addresses of a name: from the provider while encrypted DNS is on,
    else from the system. OSError when there are none."""
    try:
        return [str(ipaddress.ip_address(name.strip("[]")))]
    except ValueError:
        pass
    if active():
        return addresses(name)
    try:
        return [i[4][0] for i in socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)]
    except UnicodeError as exc:
        raise OSError(str(exc)) from None


def urlopen(req, timeout):
    """urllib.request.urlopen, connecting to the provider's address for the
    name while encrypted DNS is on (unless a proxy resolves names itself)."""
    if not active():
        return urllib.request.urlopen(req, timeout=timeout)
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    scheme, host = url.split(":", 1)[0], urllib.parse.urlsplit(url).hostname
    proxies = urllib.request.getproxies()
    if proxies.get(scheme) and not urllib.request.proxy_bypass(host or ""):
        return urllib.request.urlopen(req, timeout=timeout)
    from .userscripts import _pinned_handlers
    return urllib.request.build_opener(*_pinned_handlers(True)).open(req, timeout=timeout)


# --- for requests made with Qt's network manager -------------------------

def lookup_async(name, done):
    """done(addresses or None), in the interface's thread."""
    from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal, pyqtSlot

    global _BRIDGE
    if _BRIDGE is None:
        class Bridge(QObject):
            ready = pyqtSignal(object, object)

            @pyqtSlot(object, object)
            def deliver(self, cb, result):
                cb(result)
        _BRIDGE = Bridge()
        _BRIDGE.moveToThread(QCoreApplication.instance().thread())
        # queued: the answer is handled in the interface's thread, where the
        # network manager lives
        _BRIDGE.ready.connect(_BRIDGE.deliver, Qt.ConnectionType.QueuedConnection)

    def work():
        try:
            result = lookup(name)
        except OSError:
            result = None
        _BRIDGE.ready.emit(done, result)
    threading.Thread(target=work, daemon=True).start()


_BRIDGE = None


def pin(req, address):
    """Send a Qt request to `address` instead of looking its name up: the
    name stays in the Host header and in the encrypted connection (server
    name and certificate check). HTTP/1.1 only: HTTP/2 would name the address."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtNetwork import QNetworkRequest
    url = req.url()
    host = url.host()
    target = QUrl(url)
    target.setHost(address)
    req.setUrl(target)
    authority = host if url.port() == -1 else "%s:%d" % (host, url.port())
    req.setRawHeader(b"Host", authority.encode("idna"))
    req.setPeerVerifyName(host)
    req.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
    return req


def unpin(url, host):
    """The address a pinned request reached, with its name again."""
    from PyQt6.QtCore import QUrl
    out = QUrl(url)
    out.setHost(host)
    return out


def get(network, req, done, custom=None, data=b""):
    """Send a Qt request, its name resolved by the provider while encrypted
    DNS is on: done(reply), or done(None) when the name has no address.
    custom: a method name for sendCustomRequest."""
    def send(request):
        if custom:
            return network.sendCustomRequest(request, custom, data)
        return network.get(request)
    host = req.url().host()
    try:
        ipaddress.ip_address(host.strip("[]"))
        literal = True
    except ValueError:
        literal = False
    if not active() or literal or not host:
        done(send(req))
        return
    from .userscripts import _behind_proxy
    if _behind_proxy(host, network):
        done(send(req))                  # the proxy resolves the name (and the checks knew it)
        return

    def found(addrs):
        if not addrs:
            done(None)
            return
        done(send(pin(req, addrs[0])))
    lookup_async(host, found)
