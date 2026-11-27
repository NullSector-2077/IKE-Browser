"""Offline snapshots of real pages for the dark-mode study (not part of the tests).

    python3 tests/dark_engine/snapshot.py OUT_DIR [name ...]

Saves each page of SITES with its style sheets (those of other sites too, and
their @import and url()), images, icons and scripts, under OUT_DIR/<name>/,
rewritten so that render.py serves them from two local origins: the page's own
site on one port, every other site on another (a style sheet of another site
stays cross-origin, as on the web). Nothing is sent but plain GETs without
cookies; no login. The snapshots are not kept in the repository (they are
other people's pages): make them again with this script.
"""

import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SITES = {
    "arch-home": "https://archlinux.org/",
    "arch-packages": "https://archlinux.org/packages/?q=python",
    "arch-news": "https://archlinux.org/news/",
    "arch-package": "https://archlinux.org/packages/core/x86_64/pacman/",
    "mirror-index": "https://geo.mirror.pkgbuild.com/",
    "browserleaks-home": "https://browserleaks.com/",
    "browserleaks-js": "https://browserleaks.com/javascript",
    "eff-cyt": "https://coveryourtracks.eff.org/",
    "eff-learn": "https://coveryourtracks.eff.org/learn",
    "creepjs": "https://abrahamjuliot.github.io/creepjs/",
    # big sites (round 3): their pictures and style sheets of other hosts may be
    # missing where the network refuses those hosts (say so with the results)
    "wiki-article": "https://en.wikipedia.org/wiki/Arch_Linux",
    "github-repo": "https://github.com/NullSector-2077/IKE-Browser",
    "mdn-page": "https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color",
    "hn-front": "https://news.ycombinator.com/",
    "youtube-watch": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "pydocs-real": "https://docs.python.org/3/library/re.html",
}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
MAX_FILES, MAX_BYTES = 250, 16 << 20
CTX = ssl.create_default_context()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return r.read(MAX_BYTES), r.headers.get_content_type()


def local_path(url):
    """https://host/a/b?c -> host/<quoted path and query>"""
    u = urllib.parse.urlsplit(url)
    rest = u.path or "/"
    if rest.endswith("/"):
        rest += "index"
    elif "." not in rest.rsplit("/", 1)[-1]:
        rest += "/index"                   # /a/b and /a/b/c can both be pages (MDN): b is a folder
    if u.query:
        rest += "@" + urllib.parse.quote(u.query, safe="")
    path = urllib.parse.quote(rest.lstrip("/"), safe="/@.-_")
    # a name too long for the disk (Wikipedia's load.php?modules=...): its hash, the extension kept
    parts = path.split("/")
    for i, part in enumerate(parts):
        if len(part) > 120:
            import hashlib
            ext = ".css" if "only%3Dstyles" in part or part.endswith(".css") else ""
            parts[i] = "h" + hashlib.sha1(part.encode()).hexdigest() + ext
    return u.hostname + "/" + "/".join(parts)


class Snap:
    def __init__(self, name, url, out):
        self.name, self.url, self.out = name, url, out / name
        self.site = urllib.parse.urlsplit(url).hostname
        self.files = {}                       # url -> local path ("" while failed)
        self.queue = []

    def ref(self, url, base, kind):
        url = html.unescape(url.strip())
        if not url or url.startswith(("data:", "javascript:", "#", "mailto:", "about:", "blob:")):
            return None
        absu = urllib.parse.urljoin(base, url).split("#")[0]
        if not absu.startswith(("http://", "https://")):
            return None
        if absu not in self.files:
            if len(self.files) >= MAX_FILES:
                return None
            self.files[absu] = local_path(absu)
            self.queue.append((absu, kind))
        host = urllib.parse.urlsplit(absu).hostname
        port = "__FP__" if host == self.site else "__TP__"
        return "http://127.0.0.1:%s/snap/%s/%s" % (port, self.name, self.files[absu])

    def css(self, text, base):
        def rep(m):
            r = self.ref(m.group(2), base, "res")
            return "url(%s%s%s)" % (m.group(1), r, m.group(1)) if r else m.group(0)

        def imp(m):
            r = self.ref(m.group(1), base, "css")
            return '@import "%s"' % r if r else m.group(0)
        text = re.sub(r'@import\s+(?:url\()?\s*["\']([^"\']+)["\']\s*\)?', imp, text)
        return re.sub(r'url\(\s*(["\']?)([^"\')]+)\1\s*\)', rep, text)

    def html(self, text, base):
        def attr(m):
            name, q, val = m.group(1), m.group(2), m.group(3)
            low = name.lower()
            if low == "srcset":
                parts = []
                for item in val.split(","):
                    bits = item.strip().split()
                    if bits:
                        r = self.ref(bits[0], base, "res")
                        parts.append(" ".join([r or bits[0]] + bits[1:]))
                return '%s=%s%s%s' % (name, q, ", ".join(parts), q)
            if low == "style":
                return '%s=%s%s%s' % (name, q, self.css(val, base), q)
            kind = "res"
            r = self.ref(val, base, kind)
            return '%s=%s%s%s' % (name, q, r, q) if r else m.group(0)

        def tag(m):
            t = m.group(0)
            low = t.lower()
            if low.startswith("<a ") or low.startswith("<form"):
                return t                           # links are not followed
            if low.startswith("<link") and not re.search(r'rel=["\']?[^"\'>]*(stylesheet|icon|preload)', low):
                return t
            if re.search(r"integrity=", low):
                t = re.sub(r'\s(integrity|crossorigin)(=("[^"]*"|\'[^\']*\'|[^\s>]+))?', "", t)
            return re.sub(r'\b(src|href|srcset|style|poster|data-src)=(["\'])(.*?)\2', attr, t, flags=re.S | re.I)
        text = re.sub(r"<(?:link|script|img|source|a|form|video|audio|input|image|use|div|span|section|"
                      r"header|footer|body|td|th|table|li|p)\b[^>]*>", tag, text, flags=re.I)
        text = re.sub(r"(<style[^>]*>)(.*?)(</style>)", lambda m: m.group(1) + self.css(m.group(2), base) + m.group(3),
                      text, flags=re.S | re.I)
        text = re.sub(r'<base\s[^>]*>', "", text, flags=re.I)
        # a policy of the site would forbid the local copies
        return re.sub(r'<meta[^>]+http-equiv=["\']?content-security-policy[^>]*>', "", text, flags=re.I)

    def run(self):
        body, _ = get(self.url)
        text = body.decode("utf-8", "replace")
        page = self.html(text, self.url)
        while self.queue:
            u, kind = self.queue.pop(0)
            try:
                data, ctype = get(u)
            except Exception as e:                     # noqa: BLE001 (a missing file stays missing)
                print("  skip", u[:100], type(e).__name__)
                continue
            if kind == "css" or ctype == "text/css" or u.split("?")[0].endswith(".css"):
                data = self.css(data.decode("utf-8", "replace"), u).encode()
            p = self.out / "files" / self.files[u]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        entry = local_path(self.url)
        p = self.out / "files" / entry
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(page)
        (self.out / "manifest.json").write_text(json.dumps({"url": self.url, "entry": entry, "site": self.site,
                                                            "files": len(self.files)}))
        print(self.name, "files:", len(self.files))


def main():
    out = Path(sys.argv[1])
    names = sys.argv[2:] or list(SITES)
    for n in names:
        try:
            Snap(n, SITES[n], out).run()
        except Exception as e:                         # noqa: BLE001
            print(n, "FAILED", e)


if __name__ == "__main__":
    main()
