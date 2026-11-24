"""Screenshots of a page (1.1.24): the visible part, the whole page, or an
area chosen with the mouse. The picture is handed to a function (the window
asks where to save it); nothing is sent anywhere.

The whole page is taken a screen at a time: the page is scrolled, each part
is grabbed once the engine has drawn it and the parts are put together; the
elements that stay in place while the page scrolls (fixed and sticky bars)
are hidden after the first part, so they appear once, and everything is put
back as it was afterwards. A very long page is cut at MAX_PIXELS.
"""

import json

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from .i18n import T

WORLD = 1                # I.K.E.'s own script world: the page's scripts see nothing of it
STEP_MS = 160            # time for the engine to draw a part after it was scrolled to
MAX_PIXELS = 16000       # the tallest picture made (memory on old computers)

_MEASURE = ("(function(){var d=document.documentElement,b=document.body;"
            "return [Math.max(d.scrollHeight,b?b.scrollHeight:0,innerHeight),innerHeight,scrollX,scrollY];})()")
# hidden after the first part: what stays in place while the page scrolls
_HIDE = ("(function(){var k=[],all=document.querySelectorAll('body *');"
         "for(var i=0;i<all.length&&i<20000;i++){var p=getComputedStyle(all[i]).position;"
         "if(p==='fixed'||p==='sticky'){k.push([all[i],all[i].style.visibility]);"
         "all[i].style.visibility='hidden';}}"
         "var r=document.documentElement;k.push([r,r.style.scrollBehavior,1]);r.style.scrollBehavior='auto';"
         "window.__ikeShot=k;return k.length;})()")
_RESTORE = ("(function(x,y){var k=window.__ikeShot||[];for(var i=0;i<k.length;i++){"
            "if(k[i][2])k[i][0].style.scrollBehavior=k[i][1];else k[i][0].style.visibility=k[i][1];}"
            "window.__ikeShot=null;window.scrollTo(x,y);return true;})(%s,%s)")
_SCROLL = "(function(y){window.scrollTo({left:%s,top:y,behavior:'instant'});return scrollY;})(%s)"


def visible(view):
    """The visible part of the page."""
    return view.grab()


def _alive(obj):
    try:
        obj.page()
        return True
    except RuntimeError:
        return False


def whole_page(view, done):
    """The whole page, from its top to its end (up to MAX_PIXELS): done(QPixmap),
    or done(None) when the tab went away meanwhile."""
    page = view.page()
    state = {}

    def measured(r):
        if not _alive(view):
            done(None)
            return
        try:
            total, vh, sx, sy = (float(x) for x in r)
        except (TypeError, ValueError):
            done(visible(view))
            return
        if total <= vh + 1 or vh <= 0:
            done(visible(view))
            return
        first = view.grab()
        state["dpr"] = first.devicePixelRatio()
        scale = first.height() / vh                 # picture pixels for one pixel of the page
        height = min(int(total * scale), MAX_PIXELS)
        img = QImage(first.width(), height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("white"))
        state.update(img=img, scale=scale, vh=vh, total=total, sx=sx, sy=sy, height=height)
        ys = []
        y = 0.0
        while y * scale < height and y + vh < total:
            ys.append(y)
            y += vh
        ys.append(max(0.0, total - vh))
        state["ys"] = ys
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        state["cursor"] = True
        scroll(0)

    def scroll(i):
        if not _alive(view):
            finish(False)
            return
        page.runJavaScript(_SCROLL % (json.dumps(0), json.dumps(state["ys"][i])), WORLD,
                           lambda at, i=i: QTimer.singleShot(STEP_MS, lambda: grab(i, at)))

    def grab(i, at):
        if not _alive(view):
            finish(False)
            return
        try:
            y = float(at)
        except (TypeError, ValueError):
            y = state["ys"][i]
        piece = view.grab()
        piece.setDevicePixelRatio(1.0)              # drawn pixel for pixel
        p = QPainter(state["img"])
        p.drawPixmap(QPoint(0, int(round(y * state["scale"]))), piece)
        p.end()
        if i == 0:
            # the bars that stay in place: kept in the first part only
            page.runJavaScript(_HIDE, WORLD, lambda _n: next_part(i))
        else:
            next_part(i)

    def next_part(i):
        if i + 1 < len(state["ys"]) and state["ys"][i + 1] * state["scale"] < state["height"]:
            scroll(i + 1)
        else:
            finish(True)

    def finish(ok):
        if state.pop("cursor", False):
            QApplication.restoreOverrideCursor()
        if not ok:
            done(None)
            return
        pm = QPixmap.fromImage(state["img"])
        pm.setDevicePixelRatio(state["dpr"])
        # the page as it was (its place, its bars) before the picture is handed on
        page.runJavaScript(_RESTORE % (json.dumps(state["sx"]), json.dumps(state["sy"])), WORLD,
                           lambda _r: QTimer.singleShot(STEP_MS, lambda: done(pm)))

    page.runJavaScript(_MEASURE, WORLD, measured)


class AreaPicker(QWidget):
    """Over the page, a still picture of it: drag over the part to keep;
    Esc, a right click or a click without dragging cancels."""

    MIN = 4          # px: a smaller rectangle is a click, not a choice

    def __init__(self, view, window, done):
        super().__init__(window)
        self.setObjectName("ike_area_picker")
        self.shot = view.grab()
        self.done = done
        self.start = None
        self.rect_ = QRect()
        self.setGeometry(QRect(view.mapTo(window, QPoint(0, 0)), view.size()))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.hint = T("Drag over the part you want. Esc cancels.")
        self.show()
        self.raise_()
        self.setFocus()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        r = self.rect_.normalized()
        shade = QColor(0, 0, 0, 110)
        if r.isEmpty():
            p.fillRect(self.rect(), shade)
            f = p.font()
            f.setPointSizeF(f.pointSizeF() * 1.2)
            p.setFont(f)
            box = p.fontMetrics().boundingRect(QRect(0, 0, max(200, self.width() - 40), 400),
                                               Qt.TextFlag.TextWordWrap, self.hint)
            box.adjust(-14, -8, 14, 8)
            box.moveCenter(QPoint(self.width() // 2, min(self.height() // 2, 60 + box.height() // 2)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawRoundedRect(box, 8, 8)
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.hint)
            return
        for part in (QRect(0, 0, self.width(), r.top()),
                     QRect(0, r.bottom() + 1, self.width(), self.height() - r.bottom() - 1),
                     QRect(0, r.top(), r.left(), r.height()),
                     QRect(r.right() + 1, r.top(), self.width() - r.right() - 1, r.height())):
            p.fillRect(part, shade)
        p.setPen(QPen(self.palette().highlight().color(), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            self.finish(None)
            return
        self.start = e.position().toPoint()
        self.rect_ = QRect(self.start, self.start)
        self.update()

    def mouseMoveEvent(self, e):
        if self.start is not None:
            self.rect_ = QRect(self.start, e.position().toPoint()).intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, e):
        if self.start is None:
            return
        end = e.position().toPoint()
        r = QRect(min(self.start.x(), end.x()), min(self.start.y(), end.y()),
                  abs(end.x() - self.start.x()), abs(end.y() - self.start.y())).intersected(self.rect())
        self.start = None
        if r.width() < self.MIN or r.height() < self.MIN:
            self.finish(None)
            return
        self.finish(self.crop(r))

    def crop(self, r):
        """The part r (in this widget's pixels) of the still picture."""
        sx = self.shot.width() / max(1, self.width())
        sy = self.shot.height() / max(1, self.height())
        return self.shot.copy(QRect(round(r.x() * sx), round(r.y() * sy),
                                    round(r.width() * sx), round(r.height() * sy)))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.finish(None)
            return
        super().keyPressEvent(e)

    def finish(self, picture):
        done, self.done = self.done, None
        self.hide()
        self.deleteLater()
        if done is not None and picture is not None:
            done(picture)
