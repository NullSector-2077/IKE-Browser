"""Metrics of the dark-mode study, from the screenshots and JSON of render.py.

    python3 tests/dark_engine/metrics.py SHOTS_DIR [--modes off,dr,native,proto] [--json FILE]

Per page and mode:
  contrast_fail  text rectangles whose text/background contrast is below 3:1
                 (text colour: the 98th-percentile pixel by contrast against the
                 rectangle's dominant colour)
  light_pct      share of the page, images left out, covered by light blocks
                 (L* > 70 over a whole 9x9 neighbourhood: thin text strokes do not count)
  image_err      checked elements gone wrong: data-check=keep changed from the
                 page without dark mode (mean CIEDE2000 > 12), data-check=visible
                 no longer standing out (contrast of its pixels below 1.6:1)
  dE_mean / dE10 colour difference from Dark Reader's screenshot: mean CIEDE2000,
                 and the share of pixels with CIEDE2000 > 10 (a difference anyone
                 sees). dE10 is the figure for the "within 2-3% of Dark Reader" goal:
                 a mean dilutes a broken box in a large dark page, a share does not.
  verdict        PASS only with no contrast failure, no image error and light_pct
                 under 1 % (the owner's rule: no average hides a broken page;
                 "off" is judged on readability and images only)
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def load(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)


def lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    l = lin(rgb)
    return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]


def lab(rgb):
    l = lin(rgb)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = l @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(Cb7 / (Cb7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(C1p * C2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(C1p * C2p == 0, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2,
                                                np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Cb7p = Cbp ** 7
    Rc = 2 * np.sqrt(Cb7p / (Cb7p + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def crop(img, r, pad=0):
    x, y, w, h = r
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    return img[y0:y1, x0:x1] if x1 > x0 and y1 > y0 else None


def text_contrast(img, r):
    c = crop(img, r)
    if c is None or c.size < 30:
        return None
    px = c.reshape(-1, 3)
    q = (px // 8).astype(np.int64)
    keys = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    bg = px[keys == np.bincount(keys).argmax()].mean(0)
    Y = luminance(px)
    Yb = luminance(bg)
    ratio = (np.maximum(Y, Yb) + 0.05) / (np.minimum(Y, Yb) + 0.05)
    return float(np.percentile(ratio, 98))


def media_mask(shape, info):
    m = np.zeros(shape[:2], bool)
    for r in info.get("media", []):
        x, y, w, h = r
        m[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = True
    return m


def light_blocks(img, mask):
    L = lab(img)[..., 0] > 70
    k = 9
    pad = np.pad(L, k // 2, constant_values=False).astype(np.int32)
    s = pad.cumsum(0).cumsum(1)
    s = np.pad(s, ((1, 0), (1, 0)))
    H, W = L.shape
    tot = s[k:k + H, k:k + W] - s[0:H, k:k + W] - s[k:k + H, 0:W] + s[0:H, 0:W]
    blocks = (tot == k * k) & ~mask
    return 100.0 * blocks.sum() / max(1, (~mask).sum())


def analyse(d, page, mode, ref_off, ref_dr):
    img = load(d / ("%s__%s.png" % (page, mode)))
    info = json.loads((d / ("%s__%s.json" % (page, mode))).read_text() or "{}")
    res = {}
    cs = [(r, text_contrast(img, r)) for r in info.get("text", [])]
    res["contrast_fail"] = [[r, round(c, 2)] for r, c in cs if c is not None and c < 3.0]
    res["contrast_min"] = round(min([c for _, c in cs if c is not None], default=0), 2)
    res["light_pct"] = round(light_blocks(img, media_mask(img.shape, info)), 2)
    errs = []
    for ch in info.get("checks", []):
        r = ch["rect"]
        c = crop(img, r, 0 if ch["kind"] == "keep" else 3)
        if c is None:
            continue
        if ch["kind"] == "keep" and ref_off is not None:
            o = crop(ref_off, r)
            if o is not None and o.shape == c.shape:
                de = float(ciede2000(lab(o), lab(c)).mean())
                if de > 12:
                    errs.append("%s changed (dE %.0f)" % (ch["tag"].lower(), de))
        elif ch["kind"] == "visible":
            Y = luminance(c.reshape(-1, 3))
            ratio = (np.percentile(Y, 98) + 0.05) / (np.percentile(Y, 2) + 0.05)
            if ratio < 1.6:
                errs.append("%s invisible (%.2f:1)" % (ch["tag"].lower(), ratio))
    res["image_err"] = errs
    if ref_dr is not None and mode != "dr":
        de = ciede2000(lab(ref_dr), lab(img))
        res["dE_mean"] = round(float(de.mean()), 2)
        res["dE10"] = round(100.0 * float((de > 10).mean()), 2)
    ok = not res["contrast_fail"] and not errs and (mode == "off" or res["light_pct"] < 1.0)
    res["verdict"] = "PASS" if ok else "FAIL"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--modes", default="off,dr,native,proto")
    ap.add_argument("--json")
    a = ap.parse_args()
    d = Path(a.dir)
    modes = a.modes.split(",")
    pages = sorted({p.name.split("__")[0] for p in d.glob("*__off.png")} - {"calib", "bench"})
    out = {}
    print("%-14s" % "page" + "".join("%-34s" % m for m in modes))
    for page in pages:
        off = load(d / ("%s__off.png" % page))
        dr = load(d / ("%s__dr.png" % page)) if (d / ("%s__dr.png" % page)).exists() else None
        out[page] = {}
        cells = []
        for m in modes:
            if not (d / ("%s__%s.png" % (page, m))).exists():
                cells.append("-")
                continue
            r = out[page][m] = analyse(d, page, m, off, dr)
            cell = "%s c<3:%d min%.1f L%.1f%%" % (r["verdict"], len(r["contrast_fail"]), r["contrast_min"],
                                                 r["light_pct"])
            if "dE10" in r:
                cell += " dE%.1f/%.1f%%" % (r["dE_mean"], r["dE10"])
            if r["image_err"]:
                cell += " IMG"
            cells.append(cell)
        print("%-14s" % page + "".join("%-34s" % c for c in cells))
    for page, ms in out.items():
        for m, r in ms.items():
            if r["image_err"] or r["contrast_fail"]:
                print("  %s/%s: %s %s" % (page, m, r["image_err"], r["contrast_fail"][:3]))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
