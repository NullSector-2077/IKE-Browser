"""A photo of the user's as the background of the new tab page.

The photo chosen in Settings is copied once into I.K.E.'s data folder, scaled
down if it is larger than a 4K screen, and shown only by the new tab page
(address "ike:background", which only I.K.E.'s own pages may load). It is
never sent anywhere. The page's colours stay those of the interface theme: a
veil in the page's own background colour, as strong as the user chooses, keeps
the text readable.

Unless the user chooses otherwise, I.K.E.'s own picture is shown (DEFAULT, kept
with the program, nothing copied).

Settings: "newtab_bg" (name of the copy in the data folder, DEFAULT = I.K.E.'s
own picture, "" = none),
"newtab_bg_fit" (fill / fit / centre), "newtab_bg_veil" (0-90, per cent).
"""

import os
from pathlib import Path

from .config import DATA_DIR, RES_DIR

MAX_SIDE = 3840                  # longest side of the stored copy, in pixels
MAX_FILE = 200 * 1024 * 1024     # larger files are refused without being opened
NAME = "newtab-background"
DEFAULT = "default"              # I.K.E.'s own picture, kept with the program
DEFAULT_FILE = RES_DIR / "newtab-background.jpg"
VEIL_MAX = 90
_CSS_SIZE = {"fill": "cover", "fit": "contain", "centre": "auto"}     # the three placements
_MIME = {".jpg": b"image/jpeg", ".png": b"image/png"}

# reasons a file is refused (translated where they are shown)
NOT_FOUND = "The file was not found."
NOT_A_PICTURE = "This file is not a picture I.K.E. can open."
TOO_LARGE = "This picture is too large."
NOT_SAVED = "The picture could not be saved."


def filters():
    """File name patterns of the picture formats Qt can read here."""
    from PyQt6.QtGui import QImageReader
    kinds = sorted({bytes(f).decode("ascii", "ignore").lower() for f in QImageReader.supportedImageFormats()})
    return " ".join("*." + k for k in kinds if k and k not in ("svg", "svgz", "pdf", "ico", "cur"))


def _reader(path):
    from PyQt6.QtGui import QImageReader
    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)      # by what the file is, not by its name
    reader.setAutoTransform(True)                # photos taken with the camera turned
    return reader


def probe(path):
    """(width, height) of the picture in a file, or the reason it cannot be used."""
    try:
        p = Path(path)
        if not p.is_file():
            return None, NOT_FOUND
        if p.stat().st_size > MAX_FILE:
            return None, TOO_LARGE
    except (OSError, ValueError, TypeError):
        return None, NOT_FOUND
    reader = _reader(p)
    if not reader.canRead() or bytes(reader.format()).lower() in (b"svg", b"svgz", b"pdf"):
        return None, NOT_A_PICTURE
    size = reader.size()
    if not size.isValid() or size.width() < 1 or size.height() < 1:
        return None, NOT_A_PICTURE
    return (size.width(), size.height()), ""


def load_scaled(path, longest):
    """The picture, decoded no larger than needed (longest side), or None."""
    from PyQt6.QtCore import QSize, Qt
    size, problem = probe(path)
    if problem:
        return None, problem
    reader = _reader(path)
    w, h = size
    if max(w, h) > longest:
        scale = longest / float(max(w, h))
        # asked of the decoder itself: a JPEG is then never unpacked at full size
        reader.setScaledSize(QSize(max(1, round(w * scale)), max(1, round(h * scale))))
    image = reader.read()
    if image.isNull():
        # Qt refuses pictures that would need more memory than its limit
        return None, TOO_LARGE if w * h > 64_000_000 else NOT_A_PICTURE
    if max(image.width(), image.height()) > longest:     # a format that cannot scale while decoding
        image = image.scaled(longest, longest, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image, ""


def set_photo(config, path, folder=None):
    """Copy the picture of path into the data folder as the new background.
    Returns "" or the reason it was not done (nothing is changed then)."""
    folder = Path(folder or DATA_DIR)
    image, problem = load_scaled(path, MAX_SIDE)
    if problem:
        return problem
    alpha = image.hasAlphaChannel()
    name = NAME + (".png" if alpha else ".jpg")
    tmp = folder / (name + ".part")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        ok = image.save(str(tmp), "PNG") if alpha else image.save(str(tmp), "JPEG", 90)
        if not ok:
            raise OSError("not written")
        os.replace(tmp, folder / name)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return NOT_SAVED
    for other in (".jpg", ".png"):
        if NAME + other != name:
            try:
                (folder / (NAME + other)).unlink()
            except OSError:
                pass
    config["newtab_bg"] = name
    return ""


def _forget_copy(folder):
    for ext in (".jpg", ".png", ".jpg.part", ".png.part"):
        try:
            (folder / (NAME + ext)).unlink()
        except OSError:
            pass


def remove_photo(config, folder=None):
    """No photo at all."""
    _forget_copy(Path(folder or DATA_DIR))
    config["newtab_bg"] = ""


def use_default(config, folder=None):
    """Back to I.K.E.'s own picture; the user's copy is deleted."""
    _forget_copy(Path(folder or DATA_DIR))
    config["newtab_bg"] = DEFAULT


def is_default(config):
    return config.get("newtab_bg") == DEFAULT


def current(config, folder=None):
    """The stored photo's file, or None (none chosen, or the file is gone)."""
    name = config.get("newtab_bg")
    if name == DEFAULT:
        return DEFAULT_FILE if DEFAULT_FILE.is_file() else None
    if not isinstance(name, str) or name not in (NAME + ".jpg", NAME + ".png"):
        return None                              # only our own two names, never a path
    path = Path(folder or DATA_DIR) / name
    try:
        return path if path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None


def content(config, folder=None):
    """(bytes, mime type) of the stored photo, or (None, None)."""
    path = current(config, folder)
    if path is None:
        return None, None
    try:
        return path.read_bytes(), _MIME[path.suffix]
    except OSError:
        return None, None


def style(config, folder=None):
    """The <style> element that puts the photo behind the new tab page, or ""."""
    path = current(config, folder)
    if path is None:
        return ""
    fit = config.get("newtab_bg_fit")
    size = _CSS_SIZE.get(fit if isinstance(fit, str) else "", "cover")
    try:
        veil = max(0, min(VEIL_MAX, int(config.get("newtab_bg_veil") or 0)))
        stamp = path.stat().st_mtime_ns // 1000
    except (TypeError, ValueError, OSError):
        veil, stamp = 0, 0
    # the veil is a layer of the same background (not an element of its own over
    # the page): one painted surface, about 15-20 MB less memory per page
    veil_colour = "color-mix(in srgb,var(--bg) %d%%,transparent)" % veil
    return ('<style>html{background:linear-gradient(%s,%s) fixed,'
            'var(--bg) url("ike:background?%d") center / %s no-repeat fixed}'
            'body{background:transparent}'
            '</style>' % (veil_colour, veil_colour, stamp, size))


# --- readable text over any photo (1.1.24) -------------------------------------------------
# Over a photo each group of text on the page (the wordmark, the greeting, the clock, the tile
# names, the counter, the buttons) sits on a soft pane in the page's own background colour. How
# strong the pane must be depends on the photo under that very group, so the page works it out
# itself (newtab.html, "glass"): from this grid of the photo, one byte per cell, the brightest
# channel of the cell for light text and the darkest for dark text (a bound of what the text can
# be laid on), it finds, for each group where it really is, the weakest pane with which every
# text of the group reads at 4.5:1 (small text) or 3:1 (large figures), WCAG's level AA. A group
# over a part of the photo that is dark enough for a dark theme gets no pane at all.
_grid_cache = {}
GRID_SIDE = 64


def grid(path, light):
    """(width, height, hex of one byte per cell) of the photo, at most GRID_SIDE cells on its long
    side, or None. Transparent parts count as white (light text) or black (dark text)."""
    try:
        st = Path(path).stat()
        key = (str(path), st.st_mtime_ns, st.st_size, bool(light))
    except OSError:
        return None
    if key in _grid_cache:
        return _grid_cache[key]
    image, problem = load_scaled(path, GRID_SIDE)
    out = None
    if not problem:
        from PyQt6.QtCore import Qt
        if max(image.width(), image.height()) > GRID_SIDE:
            image = image.scaled(GRID_SIDE, GRID_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        cells = bytearray()
        for y in range(image.height()):
            for x in range(image.width()):
                c = image.pixelColor(x, y)
                a = c.alphaF()
                rgb = [c.red(), c.green(), c.blue()]
                base = 255 if light else 0
                v = max(rgb) if light else min(rgb)
                cells.append(round(v * a + base * (1 - a)))
        out = (image.width(), image.height(), bytes(cells).hex())
    if len(_grid_cache) > 4:
        _grid_cache.clear()
    _grid_cache[key] = out
    return out


def glass_data(config, light):
    """The JSON the page needs to put a pane behind its texts, or "" without a photo: the grid, the
    size of the stored picture, its placement and the veil."""
    path = current(config)
    if path is None:
        return ""
    cells = grid(path, light)
    size, problem = probe(path)
    if cells is None or problem:
        return ""
    fit = config.get("newtab_bg_fit")
    fit = {"fill": "cover", "fit": "contain", "centre": "auto"}.get(fit if isinstance(fit, str) else "", "cover")
    import json
    return json.dumps({"gw": cells[0], "gh": cells[1], "g": cells[2], "pw": size[0], "ph": size[1],
                       "fit": fit, "veil": veil_of(config), "light": bool(light)})


def veil_of(config):
    """The veil the user chose, per cent, as style() uses it."""
    try:
        return max(0, min(VEIL_MAX, int(config.get("newtab_bg_veil") or 0)))
    except (TypeError, ValueError):
        return 0
