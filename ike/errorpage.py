"""I.K.E.'s own look for the pages shown when a site cannot be reached (site
not found, no connection, connection refused, too slow, interrupted).

The engine still makes its error page, so the address, the history and
Reload stay what they are; I.K.E. only puts its own text on it, in the
colours of the theme in use, with a "Try again" link to the same address.
Certificate errors keep the engine's own warning: there safety comes first.
"""

import html
import json

from .i18n import T

# Chromium's network error codes (net/base/net_error_list.h)
KINDS = {
    -105: "not_found", -137: "not_found",                  # NAME_NOT_RESOLVED, NAME_RESOLUTION_FAILED
    -106: "offline", -21: "offline",                       # INTERNET_DISCONNECTED, NETWORK_CHANGED
    -102: "refused",                                       # CONNECTION_REFUSED
    -118: "slow", -7: "slow",                              # CONNECTION_TIMED_OUT, TIMED_OUT
    -101: "cut", -100: "cut", -109: "cut", -324: "cut",    # RESET, CLOSED, ADDRESS_UNREACHABLE, EMPTY_RESPONSE
}
SKIP = {-3, -20, -27, -301}       # ABORTED, BLOCKED_BY_CLIENT, BLOCKED_BY_RESPONSE, DISALLOWED_URL_SCHEME


def texts(kind):
    return {
        "not_found": (T("Site not found"), T("The address could not be found. Check that it is written "
                                            "correctly, or try again in a moment.")),
        "offline": (T("No connection"), T("This computer does not seem to be connected to the Internet. "
                                         "Check the network, then try again.")),
        "refused": (T("Connection refused"), T("The site refused the connection. It may be down for a "
                                              "while.")),
        "slow": (T("The site does not answer"), T("The site took too long to answer. Try again in a "
                                                 "moment.")),
        "cut": (T("Connection interrupted"), T("The connection was interrupted before the page arrived. "
                                              "Try again.")),
    }.get(kind, (T("This page could not be opened"), T("Something went wrong on the way to the site.")))


def wanted(info):
    """Is this failed load one that gets I.K.E.'s page?"""
    from PyQt6.QtWebEngineCore import QWebEngineLoadingInfo as L
    if info.status() != L.LoadStatus.LoadFailedStatus or not info.isErrorPage():
        return False
    if info.errorDomain() not in (L.ErrorDomain.ConnectionErrorDomain, L.ErrorDomain.DnsErrorDomain,
                                  L.ErrorDomain.InternalErrorDomain, L.ErrorDomain.HttpErrorDomain):
        return False
    return info.errorCode() not in SKIP and info.url().scheme() in ("http", "https")


def page_html(info, palette):
    from PyQt6.QtGui import QPalette
    R = QPalette.ColorRole
    title, text = texts(KINDS.get(info.errorCode()))
    url = info.url().toString()
    c = {k: palette.color(r).name() for k, r in (("bg", R.Window), ("fg", R.WindowText), ("acc", R.Highlight),
                                                    ("card", R.Base), ("line", R.Mid), ("acctext", R.HighlightedText))}
    esc = html.escape
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>%(title)s</title><style>"
        "html{background:%(bg)s;color:%(fg)s}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "font-family:system-ui,'Noto Sans',sans-serif}"
        "main{width:min(560px,88vw)}"
        ".mark{width:56px;height:56px;border-radius:50%%;border:2px solid %(acc)s;color:%(acc)s;display:flex;"
        "align-items:center;justify-content:center;font-size:30px;font-weight:600;margin-bottom:22px}"
        "h1{font-size:26px;font-weight:600;margin:0 0 10px}"
        "p{font-size:15px;line-height:1.5;margin:0 0 18px;opacity:.85}"
        ".url{font-size:13px;padding:8px 12px;border-radius:8px;background:%(card)s;border:1px solid %(line)s;"
        "word-break:break-all;margin-bottom:22px}"
        "a.go{display:inline-block;padding:9px 20px;border-radius:999px;background:%(acc)s;color:%(acctext)s;"
        "text-decoration:none;font-weight:600}"
        "a.go:focus-visible{outline:2px solid %(fg)s;outline-offset:2px}"
        ".code{font-size:12px;opacity:.55;margin-top:26px}"
        "</style></head><body><main>"
        "<div class='mark'>!</div><h1>%(title)s</h1><p>%(text)s</p>"
        "<div class='url'>%(url)s</div>"
        "<a class='go' href='%(href)s'>%(retry)s</a>"
        "<div class='code'>%(code)s</div>"
        "</main></body></html>"
    ) % dict(c, title=esc(title), text=esc(text), url=esc(url), href=esc(url, quote=True),
             retry=esc(T("Try again")), code=esc("%s (%d)" % (info.errorString() or "", info.errorCode())))


def script(info, palette):
    """The script that puts I.K.E.'s page in place of the engine's text."""
    return ("(function (h) { document.open(); document.write(h); document.close(); })(%s);"
            % json.dumps(page_html(info, palette)))
