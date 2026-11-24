"""Right-click menu of web pages, built by I.K.E. itself."""

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QAction, QGuiApplication, QIcon
from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as Req
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import QMenu

from . import handoff
from .i18n import T

WA = QWebEnginePage.WebAction


def _ic(name):
    from .icons import themed
    return themed(name)


def clean_link(url):
    """The address without its tracking parameters (shields.strip_tracking);
    the same address when it has none."""
    from .shields import strip_tracking
    return strip_tracking(url) or url


def build(view, req):
    """Return the menu for a context-menu request (never None)."""
    win = view.window_ref
    app = win.app
    page = view.page()
    menu = QMenu(view)
    menu.setToolTipsVisible(True)

    def add(text, slot, icon=None, enabled=True, tip=None):
        a = QAction(_ic(icon) if icon else QIcon(), text, menu)
        a.setEnabled(enabled)
        if tip:
            a.setToolTip(tip)
        a.triggered.connect(lambda _c=False: slot())
        menu.addAction(a)
        return a

    def engine(action):
        return lambda: page.triggerAction(action)

    def copy_text(text, action=None):
        def run():
            if action is not None:
                page.triggerAction(action)
            cb = QGuiApplication.clipboard()
            QTimer.singleShot(120, lambda: view._ensure_copied(text=text) if action is not None
                              else cb.setText(text))
            if action is None:
                cb.setText(text)
        return run

    link = req.linkUrl() if req else QUrl()
    has_link = link.isValid() and not link.isEmpty()
    media = req.mediaUrl() if req else QUrl()
    mtype = req.mediaType() if req else Req.MediaType.MediaTypeNone
    sel = (req.selectedText() if req else "") or ""
    editable = bool(req and req.isContentEditable())
    eflags = req.editFlags() if req else Req.EditFlag(0)
    mflags = req.mediaFlags() if req else Req.MediaFlag(0)
    container = getattr(view, "container", None)

    # --- link ---------------------------------------------------------
    if has_link:
        add(T("Open link in new tab"), lambda: win.add_tab(link, background=True, after=view,
                                                           container=container), "tab-new")
        add(T("Open link in new window"),
            lambda: app.new_window(private=win.private, urls=[link]), "window-new")
        add(T("Open link in private window"),
            lambda: app.new_window(private=True, urls=[link]), ("view-private", "preferences-system-privacy-symbolic"))
        if not win.private and win.ext_on("containers"):
            from .features import CONTAINER_ICON, colour_dot
            sub = menu.addMenu(_ic(CONTAINER_ICON), T("Open link in container"))
            for c in app.config["containers"]:
                # 1.1.25: each with its colour, as in the tab menu's "Reopen in container"
                a = sub.addAction(colour_dot(c.get("color")), c["name"])
                a.triggered.connect(lambda _c=False, n=c["name"]: win.add_tab(
                    link, background=True, after=view, container=n))
        if win.ext_on("split"):
            add(T("Open link in split view"),
                lambda: win.split_with(win.add_tab(link, background=True, after=view,
                                                   container=container)),
                ("view-split-left-right", "view-dual-symbolic"))
        menu.addSeparator()
        add(T("Copy link address"), copy_text(link.toString()), "edit-copy")
        if link.scheme() in ("http", "https"):
            # without utm_, fbclid, gclid... (shields.TRACKING_PARAMS, the same list
            # that cleans links when they are opened), as in the address bar (1.1.24)
            add(T("Copy clean link"), copy_text(clean_link(link.toString())), "edit-copy",
                tip=T("Copy the address without tracking parameters"))
        add(T("Save link as…"), engine(WA.DownloadLinkToDisk), "document-save")
        if link.scheme() in ("http", "https", "file") and link.path().lower().endswith(".ics"):
            # an event or a calendar: to the desktop's calendar app, when there is one (1.1.24)
            if handoff.app_for(handoff.CALENDAR) is not None:
                add(T("Add to calendar"), lambda: app.hand_off(link, "calendar", page),
                    ("view-calendar", "x-office-calendar", "office-calendar"))
        if not win.private:
            app.desktop.add_send_menu(menu, link.toString())
        add(T("Bookmark this link"),
            lambda: (app.storage.add_bookmark(link.toString(), (req.linkText() or link.toString())),
                     app.refresh_windows()), "bookmark-new")
        menu.addSeparator()

    # --- image / video / audio ---------------------------------------------
    MT = Req.MediaType
    has_media = media.isValid() and not media.isEmpty()
    if mtype == MT.MediaTypeImage:
        if has_media:
            add(T("Open image in new tab"), lambda: win.add_tab(media, background=True, after=view,
                                                                container=container), "tab-new")
        if has_media and media.scheme() in ("http", "https", "file"):
            # the desktop's image viewer (Gwenview on KDE), when there is one (1.1.24)
            viewer = handoff.app_for(handoff.image_type(media.fileName()))
            if viewer is not None:
                add(T("Open image in %s") % viewer.name, lambda: app.hand_off(media, "image", page),
                    ("image-x-generic", "view-preview"))
        add(T("Save image as…"), engine(WA.DownloadImageToDisk), "document-save")
        add(T("Copy image"), engine(WA.CopyImageToClipboard), "edit-copy")
        if has_media:
            add(T("Copy image address"), copy_text(media.toString()), "edit-copy")
        menu.addSeparator()
    elif mtype in (MT.MediaTypeVideo, MT.MediaTypeAudio):
        MF = Req.MediaFlag
        add(T("Play") if mflags & MF.MediaPaused else T("Pause"), engine(WA.ToggleMediaPlayPause),
            "media-playback-start" if mflags & MF.MediaPaused else "media-playback-pause")
        add(T("Unmute") if mflags & MF.MediaMuted else T("Mute"), engine(WA.ToggleMediaMute),
            "audio-volume-muted")
        loop = add(T("Loop"), engine(WA.ToggleMediaLoop))
        loop.setCheckable(True)
        loop.setChecked(bool(mflags & MF.MediaLoop))
        ctl = add(T("Show controls"), engine(WA.ToggleMediaControls))
        ctl.setCheckable(True)
        ctl.setChecked(bool(mflags & MF.MediaControls))
        if mtype == MT.MediaTypeVideo and win.ext_on("pip"):
            add(T("Video in floating window"), win.float_video,
                ("picture-in-picture", "window-duplicate", "focus-windows-symbolic"))
        if has_media:
            add(T("Save media as…"), engine(WA.DownloadMediaToDisk), "document-save",
                bool(mflags & MF.MediaCanSave) or True)
            add(T("Copy media address"), copy_text(media.toString()), "edit-copy")
        menu.addSeparator()

    # --- a PDF in the engine's viewer: to the desktop's PDF app (Okular on KDE), 1.1.24 ---
    pdf = (media if mtype == MT.MediaTypePlugin and has_media
           else view.url() if view.url().path().lower().endswith(".pdf") else None)
    if (pdf is not None and not has_link and not sel and not editable
            and pdf.scheme() in ("http", "https", "file")):
        reader = handoff.app_for("application/pdf")
        if reader is not None:
            add(T("Open with %s") % reader.name, lambda: app.hand_off(pdf, "pdf", page),
                ("application-pdf", "x-office-document"))
            menu.addSeparator()

    # --- spelling ---------------------------------------------------------
    if req and editable and req.misspelledWord():
        for word in list(req.spellCheckerSuggestions())[:6]:
            add(word, lambda w=word: page.replaceMisspelledWord(w))
        menu.addSeparator()

    # --- text ------------------------------------------------------------
    EF = Req.EditFlag
    if editable:
        add(T("Undo"), engine(WA.Undo), "edit-undo", bool(eflags & EF.CanUndo))
        add(T("Redo"), engine(WA.Redo), "edit-redo", bool(eflags & EF.CanRedo))
        menu.addSeparator()
        add(T("Cut"), copy_text(sel, WA.Cut), "edit-cut", bool(sel))
    if sel or editable:
        add(T("Copy"), copy_text(sel, WA.Copy), "edit-copy", bool(sel))
    if editable:
        add(T("Paste"), engine(WA.Paste), "edit-paste")
        add(T("Paste as plain text"), engine(WA.PasteAndMatchStyle), "edit-paste")
        add(T("Select all"), engine(WA.SelectAll), "edit-select-all")
        menu.addSeparator()
        if win.ext_on("passwords"):
            add(T("Fill login on this page"), win.fill_login,
                ("password-show-on", "dialog-password-symbolic", "object-locked"))
            add(T("Insert a generated password"), lambda: _insert_password(view),
                ("dialog-password", "object-locked"))
    if sel:
        short = sel.strip().replace("\n", " ")
        short = short if len(short) < 28 else short[:27] + "…"
        add(T("Search %s for “%s”") % (app.config.engine()["name"], short),
            lambda: win.add_tab(QUrl(app.shields.search_url(sel.strip())), after=view,
                                container=container), "edit-find")
        if not has_link and "." in sel and " " not in sel.strip() and len(sel) < 300:
            add(T("Open “%s”") % short, lambda: win.add_tab(QUrl.fromUserInput(sel.strip()),
                                                           after=view, container=container))
    if sel or editable:
        menu.addSeparator()

    # --- page ------------------------------------------------------------
    if not (has_link or sel or editable or mtype != MT.MediaTypeNone):
        h = view.history()
        add(T("Back"), engine(WA.Back), "go-previous", h.canGoBack())
        add(T("Forward"), engine(WA.Forward), "go-next", h.canGoForward())
        add(T("Reload"), engine(WA.Reload), "view-refresh")
        menu.addSeparator()
        add(T("Bookmark this page"), win.toggle_bookmark, "bookmark-new")
        if not win.private:
            app.desktop.add_send_menu(menu, view.url().toString())
        add(T("Save page as…"), engine(WA.SavePage), "document-save")
        add(T("Save as PDF…"), win.save_pdf, ("application-pdf", "document-save"))
        add(T("Print…"), win.print_page, "document-print")
        menu.addSeparator()
        add(T("Reader mode"), win.toggle_reader,
            ("view-readermode", "view-reader-symbolic", "x-office-document-symbolic"))
        if win.ext_on("translate"):
            add(T("Translate page…"), win.translate_page,
                ("translate", "preferences-desktop-locale-symbolic", "preferences-desktop-locale"))
        menu.addAction(win.act_shot)         # its submenu: visible part, whole page, an area (1.1.24)
        menu.addSeparator()
        add(T("Select all"), engine(WA.SelectAll), "edit-select-all")
        add(T("Page source"), win.view_source, ("text-html", "view-source"))
        if view.url().scheme() in ("http", "https", "file"):
            editor = handoff.app_for("text/plain")       # Kate on KDE (1.1.24)
            if editor is not None:
                add(T("Open the page source in %s") % editor.name, lambda: win.source_to_app(view),
                    ("accessories-text-editor", "text-x-generic"))
    if (not win.private and view.url().scheme() in ("http", "https")
            and app.config["page_watch_on"] and not editable):
        from .watcher import pick_and_watch
        pos = req.position() if req else None
        menu.addSeparator()
        if pos is not None:
            add(T("Notify me when this part changes…"), lambda: pick_and_watch(view, pos, True),
                ("view-visible", "view-reveal-symbolic", "document-open-recent-symbolic", "view-history"),
                tip=T("For example a price: checked in the background"))
        add(T("Notify me when this page changes…"), lambda: pick_and_watch(view, pos, False),
            ("view-visible", "view-reveal-symbolic", "document-open-recent-symbolic", "view-history"))
    add(T("Inspect element"), lambda: win.open_devtools(view),
        ("tools-report-bug", "bug-symbolic", "utilities-terminal-symbolic"))
    return menu


def _insert_password(view):
    import json

    from .passwords import copy_secret, generate_password
    pw = generate_password()
    copy_secret(pw)            # kept out of clipboard history, taken off after a while (review L9)
    view.page().runJavaScript(
        "(function(v){var e=document.activeElement;if(!e||!('value' in e))return;"
        "var d=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e),'value');"
        "if(d&&d.set)d.set.call(e,v);else e.value=v;"
        "e.dispatchEvent(new Event('input',{bubbles:true}));"
        "e.dispatchEvent(new Event('change',{bubbles:true}));})(%s);" % json.dumps(pw), 0)
    view.window_ref.app._notify(T("Password generated and copied to the clipboard."))
