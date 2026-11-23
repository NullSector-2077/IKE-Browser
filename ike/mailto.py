"""Email links ("mailto:"), 1.1.16.

Like other browsers, I.K.E. writes the email with the service the user chose:
a web mail (Gmail, Outlook.com, Proton Mail, Yahoo Mail) opens in a new tab
with the message already filled in, or the computer's mail program takes it.
Until the user chooses, I.K.E. asks at every link.

I.K.E. can also be the system's handler for email links (the desktop file
lists x-scheme-handler/mailto): a link clicked in another program then
reaches I.K.E. and goes to the chosen web mail. The computer's mail program
is never offered for those, since that would hand the link back to I.K.E.
"""

from urllib.parse import parse_qsl, quote, unquote, urlencode

# key, name shown; the names are brands and are not translated
SERVICES = (("gmail", "Gmail"), ("outlook", "Outlook.com"),
            ("proton", "Proton Mail"), ("yahoo", "Yahoo Mail"))
CHOICES = ("ask", "system") + tuple(k for k, _n in SERVICES)
MAX_LEN = 8000                       # longer links are cut; no service takes more
FIELDS = ("to", "cc", "bcc", "subject", "body")


def is_mailto(text):
    return isinstance(text, str) and text[:7].lower() == "mailto:"


def fields(mailto):
    """The parts of a mailto link: to, cc, bcc, subject, body (all text)."""
    rest = mailto[7:MAX_LEN] if is_mailto(mailto) else ""
    to, _q, query = rest.partition("?")
    out = dict.fromkeys(FIELDS, "")
    out["to"] = unquote(to).strip()
    for key, value in parse_qsl(query, keep_blank_values=True):
        key = key.lower()
        if key not in out:
            continue
        if key in ("to", "cc", "bcc"):
            out[key] = ",".join(x for x in (out[key], value.strip()) if x)
        elif not out[key]:
            out[key] = value
    return out


def compose_url(service, mailto):
    """The address of the service's writing page, or None for an unknown service."""
    mailto = mailto[:MAX_LEN]
    if service == "gmail":
        return "https://mail.google.com/mail/?extsrc=mailto&url=" + quote(mailto, safe="")
    if service == "proton":
        return "https://mail.proton.me/inbox/#mailto=" + quote(mailto, safe="")
    if service in ("outlook", "yahoo"):
        f = fields(mailto)
        query = urlencode([(k, f[k]) for k in FIELDS if f[k]], quote_via=quote)
        base = ("https://outlook.live.com/mail/0/deeplink/compose?" if service == "outlook"
                else "https://compose.mail.yahoo.com/?")
        return base + query
    return None


def choose(parent, address, from_desktop=False):
    """Ask which service writes the email: (key, remember) or (None, False)."""
    from PyQt6.QtWidgets import QMessageBox

    from .i18n import T
    from .uistyle import Switch
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(T("Write an email"))
    shown = address if len(address) <= 120 else address[:120] + "…"
    box.setText(T("Write an email to %s with:") % (shown or "…"))
    buttons = {}
    for key, name in SERVICES:
        buttons[box.addButton(name, QMessageBox.ButtonRole.AcceptRole)] = key
    if not from_desktop:
        buttons[box.addButton(T("The computer's mail program"),
                              QMessageBox.ButtonRole.AcceptRole)] = "system"
    cancel = box.addButton(T("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    remember = Switch(T("Remember this choice"))
    box.setCheckBox(remember)
    box.exec()
    key = buttons.get(box.clickedButton())
    return key, bool(key and remember.isChecked())


def open_link(app, url, win, page=None, from_desktop=False):
    """Write the email of a mailto link (a QUrl) as the user chose.

    page is the WebPage whose link was clicked (None for a link that came
    from another program)."""
    if win is None:
        return
    text = bytes(url.toEncoded()).decode("ascii", "replace")
    choice = app.config["mail_handler"]
    if choice not in CHOICES or (choice == "system" and from_desktop):
        choice = "ask"
    if choice == "ask":
        choice, remember = choose(win, fields(text)["to"], from_desktop)
        if choice is None:
            return
        if remember:
            app.config["mail_handler"] = choice
            app.config.save()
        if choice == "system":
            app.handoff.open_uri(url, win)         # the user just chose it: no second question
            return
    if choice == "system":
        if page is not None and page.ask_external(_origin(page), url):
            app.handoff.open_uri(url, win)         # the desktop portal (handoff.py, 1.1.24)
        return
    target = compose_url(choice, text)
    if target:
        current = win.current_view() if hasattr(win, "current_view") else None
        view = win.add_tab(target, after=current)
        win.set_current(view)


def _origin(page):
    from .webview import origin_text
    return origin_text(page.url())
