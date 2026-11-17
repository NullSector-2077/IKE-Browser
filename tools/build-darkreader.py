#!/usr/bin/env python3
"""Build I.K.E.'s copy of Dark Reader (MIT, https://darkreader.org) the way the
Dark Reader extension for Chromium uses it.

    python3 tools/build-darkreader.py --lib darkreader.js --config DIR [--commit SHA] [--date YYYY-MM-DD]

--lib     darkreader.js of the "darkreader" package on npm (the engine)
--config  src/config of the Dark Reader repository (the extension's lists)

Writes, in ike/resources/:

- darkreader.js        the engine. One change, the one the extension's own
                       Manifest V3 build makes: the style-sheet proxy is not
                       put into the page as an inline <script> (which strict
                       Content-Security-Policies, as on Google's sites, block),
                       it is asked for with the "__darkreader__stylesheetProxy__arg"
                       event (with a token of the session in its name, so that
                       a page cannot ask for it).
- darkreader-proxy.js  that proxy (Dark Reader's own injectProxy, taken out of
                       the engine) with the extension's listener for the
                       event. I.K.E. runs it in the page's own world, where no
                       Content-Security-Policy applies to it.
- darkreader-data.json the extension's lists: fixes for single sites
                       (dynamic-theme-fixes.config), sites with a dark theme
                       of their own (dark-sites.config) and the hints that
                       recognise a site's own dark theme (detector-hints.config).

The daily component check runs this with the newest engine on npm and the
newest lists on GitHub; the result is stopped if a step does not find what it
expects, so a changed engine is never half-adapted.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "ike" / "resources"

PROXY_BLOCK = re.compile(
    r"\{\s*const proxyScript = createOrUpdateScript\(\"darkreader--proxy\"\);.*?proxyScript\.remove\(\);\s*\}",
    re.S)
# I.K.E. adds a token of the session to the event's name (__IKE_DR_TOKEN__, put in at
# run time in both scripts): a page cannot start the proxy itself
PROXY_EVENT = ('document.dispatchEvent(new CustomEvent("__darkreader__stylesheetProxy__arg__IKE_DR_TOKEN__", '
               '{detail: {enableStyleSheetsProxy, enableCustomElementRegistryProxy}}));')

FIX_COMMANDS = {"INVERT": "invert", "CSS": "css", "IGNORE INLINE STYLE": "ignoreInlineStyle",
                "IGNORE IMAGE ANALYSIS": "ignoreImageAnalysis", "IGNORE CSS URL": "ignoreCSSUrl"}
HINT_COMMANDS = {"TARGET": "target", "MATCH": "match", "NO DARK THEME": "noDarkTheme",
                 "SYSTEM THEME": "systemTheme", "IFRAME": "iframe"}
COMMAND_LINE = re.compile(r"^[A-Z]+(\s[A-Z]+){0,2}$")


def parse_array(text):
    return [s.strip() for s in text.replace("\r", "").split("\n") if s.strip()]


def parse_blocks(text, commands, value):
    """Dark Reader's parseSitesFixesConfig, in Python."""
    out = []
    for block in re.split(r"^\s*={2,}\s*$", text.replace("\r", ""), flags=re.M):
        lines = block.split("\n")
        marks = [i for i, ln in enumerate(lines) if COMMAND_LINE.match(ln)]
        if not marks:
            continue
        entry = {"url": parse_array("\n".join(lines[:marks[0]]))}
        for n, i in enumerate(marks):
            command = lines[i].strip()
            end = marks[n + 1] if n + 1 < len(marks) else len(lines)
            prop = commands.get(command)
            if prop:
                entry[prop] = value(command, "\n".join(lines[i + 1:end]))
        out.append(entry)
    return out


def fix_value(command, text):
    return text.strip() if command == "CSS" else parse_array(text)


def hint_value(command, text):
    if command == "TARGET":
        return text.strip()
    if command in ("NO DARK THEME", "SYSTEM THEME"):
        return True
    return parse_array(text)


def extract_proxy(lib):
    """The text of Dark Reader's injectProxy function (prettier output: the
    function ends at the first line that closes it at its own indentation)."""
    lib = lib.replace("\r\n", "\n")
    start = lib.find("\n    function injectProxy(")
    if start < 0:
        raise SystemExit("injectProxy not found in the engine")
    end = lib.find("\n    }\n", start + 1)
    if end < 0:
        raise SystemExit("the end of injectProxy was not found")
    return lib[start + 1:end + 6]


def build(lib_path, config, commit="", date=""):
    lib = Path(lib_path).read_bytes().decode("utf-8")      # its own line ends kept
    m = re.search(r"Dark Reader v([0-9.]+)", lib[:400])
    if not m:
        raise SystemExit("not Dark Reader's engine")
    version = m.group(1)
    found = PROXY_BLOCK.findall(lib)
    if len(found) != 1:
        raise SystemExit("the proxy injection of the engine was not found exactly once (%d)" % len(found))
    engine = PROXY_BLOCK.sub(lambda _m: PROXY_EVENT, lib)
    proxy = extract_proxy(lib)
    proxy_js = (
        "// I.K.E.: Dark Reader's style-sheet proxy (MIT, https://darkreader.org), run in the\n"
        "// page's own world at the start of every frame of a page that is made dark. It\n"
        "// waits, as in the Dark Reader extension, for the engine to ask for it with\n"
        "// \"__darkreader__stylesheetProxy__arg\". Built by tools/build-darkreader.py from\n"
        "// Dark Reader v%s: do not edit by hand.\n"
        "(function () {\n"
        "    'use strict';\n"
        "    var KEY = 'darkreaderProxyInjected';\n"
        "%s\n"
        "    function dataReceiver(e) {\n"
        "        if (document.documentElement.dataset[KEY] !== undefined) return;\n"
        "        document.documentElement.dataset[KEY] = 'true';\n"
        "        var d = (e && e.detail) || {};\n"
        "        injectProxy(d.enableStyleSheetsProxy !== false, d.enableCustomElementRegistryProxy !== false);\n"
        "    }\n"
        "    function cleanUpReceiver() {\n"
        "        delete document.documentElement.dataset[KEY];\n"
        "    }\n"
        "    document.addEventListener('__darkreader__stylesheetProxy__arg__IKE_DR_TOKEN__', dataReceiver);\n"
        "    document.addEventListener('__darkreader__cleanUp', cleanUpReceiver);\n"
        "})();\n" % (version, proxy))
    cfg = Path(config)
    fixes = parse_blocks((cfg / "dynamic-theme-fixes.config").read_text("utf-8"), FIX_COMMANDS, fix_value)
    if not fixes or fixes[0]["url"][:1] != ["*"]:
        raise SystemExit("the site fixes do not start with the common fix")
    hints = parse_blocks((cfg / "detector-hints.config").read_text("utf-8"), HINT_COMMANDS, hint_value)
    dark = parse_array((cfg / "dark-sites.config").read_text("utf-8"))
    data = {"version": version, "lists_commit": commit, "lists_date": date,
            "fixes": fixes, "dark_sites": dark, "detector_hints": hints}
    return engine, proxy_js, data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lib", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--commit", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default=str(RES))
    a = ap.parse_args(argv)
    engine, proxy_js, data = build(a.lib, a.config, a.commit, a.date)
    out = Path(a.out)
    (out / "darkreader.js").write_bytes(engine.encode("utf-8"))
    (out / "darkreader-proxy.js").write_text(proxy_js, "utf-8")
    (out / "darkreader-data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                                              "utf-8")
    print("Dark Reader %s: %d site fixes, %d dark sites, %d detector hints"
          % (data["version"], len(data["fixes"]), len(data["dark_sites"]), len(data["detector_hints"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
