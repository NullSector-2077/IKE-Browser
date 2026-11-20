#!/usr/bin/env python3
"""Build I.K.E.'s copy of Dark Reader (MIT, https://darkreader.org) the way the
Dark Reader extension for Chromium uses it.

    python3 tools/build-darkreader.py --lib darkreader.js --config DIR [--commit SHA] [--date YYYY-MM-DD]

--lib     darkreader.js of the "darkreader" package on npm (the engine)
--config  src/config of the Dark Reader repository (the extension's lists)

Writes, in ike/resources/:

- darkreader.js        the engine. The change the extension's own Manifest V3
                       build makes: the style-sheet proxy is not put into the
                       page as an inline <script> (which strict
                       Content-Security-Policies, as on Google's sites, block),
                       it is asked for with the "__darkreader__stylesheetProxy__arg"
                       event (with a token of the session in its name, so that
                       a page cannot ask for it). And I.K.E.'s changes that make
                       the engine's work cheaper without changing what it does
                       to a page (PATCHES below).
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

# Changes that make Dark Reader's work cheaper without changing what it does to
# a page (docs/review/tests-and-performance.md has the measurements). Each one is
# (name, text of the engine, its replacement): the text must be found exactly
# once, or the build stops.
PATCHES = [
    # Finding the elements that have a shadow root: the walk asked a script
    # function about every element; without it the same walk, in the same
    # order, is about ten times faster.
    ("shadow-host-walk", """\
        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_ELEMENT,
            {
                acceptNode(node) {
                    return node.shadowRoot == null
                        ? NodeFilter.FILTER_SKIP
                        : NodeFilter.FILTER_ACCEPT;
                }
            }
        );
        for (
            let node = root.shadowRoot ? walker.currentNode : walker.nextNode();
            node != null;
            node = walker.nextNode()
        ) {
            if (node.classList.contains("surfingkeys_hints_host")) {
""", """\
        // I.K.E.: no filter function, the shadow root is checked here
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
        for (
            let node = root.shadowRoot ? walker.currentNode : walker.nextNode();
            node != null;
            node = walker.nextNode()
        ) {
            if (node.shadowRoot == null) {
                continue;
            }
            if (node.classList.contains("surfingkeys_hints_host")) {
"""),
    # After a large change of the page, a style element counted as moved when
    # the copy Dark Reader had put next to it was its new neighbour; its copy
    # was then built again from scratch (and the browser styled the page
    # again), once for every style added to the page since Dark Reader started.
    # Dark Reader's own elements are not counted as neighbours.
    ("style-moves", """\
        function saveStylePosition(style) {
            prevStyleSiblings.set(style, style.previousElementSibling);
            nextStyleSiblings.set(style, style.nextElementSibling);
        }
""", """\
        // I.K.E.: Dark Reader's own elements are not neighbours that count
        function ikeStyleSibling(style, next) {
            let el = next
                ? style.nextElementSibling
                : style.previousElementSibling;
            while (el && el.classList.contains("darkreader")) {
                el = next ? el.nextElementSibling : el.previousElementSibling;
            }
            return el;
        }
        function saveStylePosition(style) {
            prevStyleSiblings.set(style, ikeStyleSibling(style, false));
            nextStyleSiblings.set(style, ikeStyleSibling(style, true));
        }
"""),
    ("style-moves-check", """\
                style.previousElementSibling !== prevStyleSiblings.get(style) ||
                style.nextElementSibling !== nextStyleSiblings.get(style)
""", """\
                ikeStyleSibling(style, false) !== prevStyleSiblings.get(style) ||
                ikeStyleSibling(style, true) !== nextStyleSiblings.get(style)
"""),
    # SVG shapes with a fill colour: Dark Reader reads each shape's size (an
    # icon or a background?) right after changing the previous shape, so the
    # browser lays the page out again for every shape. The sizes of a group of
    # elements are read first, then the elements are changed. Dark Reader only
    # changes colours there, so the sizes are the same ones it would read.
    ("svg-sizes", """\
        const parent = svgElement.parentNode;
        const root = getSVGElementRoot(parent);
        svgNodesRoots.set(svgElement, root);
        return root;
    }
""", """\
        const parent = svgElement.parentNode;
        const root = getSVGElementRoot(parent);
        svgNodesRoots.set(svgElement, root);
        return root;
    }
    // I.K.E.: sizes read for a group of elements before any of them is changed
    let ikeSVGRects = null;
    function ikeSVGRect(el) {
        const rect = ikeSVGRects && ikeSVGRects.get(el);
        return rect || el.getBoundingClientRect();
    }
    function ikeWithSVGRects(elements, run, pending = false) {
        if (ikeSVGRects || !isReadyStateComplete()) {
            run();
            return;
        }
        const shapes = [];
        forEach(elements, (el) => {
            if (
                !(el instanceof SVGElement) ||
                el instanceof SVGTextElement ||
                !el.hasAttribute("fill")
            ) {
                return;
            }
            const fill = el.getAttribute("fill");
            if (fill === "none" || fill === "currentColor") {
                return;
            }
            if (
                !pending &&
                inlineStyleCache.get(el) === getInlineStyleCacheKey(el, theme)
            ) {
                return;
            }
            shapes.push(el);
        });
        if (shapes.length < 2) {
            run();
            return;
        }
        const rects = new Map();
        shapes.forEach((el) => {
            const root = getSVGElementRoot(el);
            if (!root) {
                return;
            }
            if (!svgRootSizeTestResults.has(root) && !rects.has(root)) {
                rects.set(root, root.getBoundingClientRect());
            }
            rects.set(el, el.getBoundingClientRect());
        });
        ikeSVGRects = rects;
        try {
            run();
        } finally {
            ikeSVGRects = null;
        }
    }
    // shapes found while the page loads are handled together when it is loaded
    const ikePendingSVG = [];
    function ikeRunPendingSVG() {
        const list = ikePendingSVG.splice(0);
        ikeWithSVGRects(
            list.map((item) => item[0]),
            () => list.forEach((item) => item[1]()),
            true
        );
    }
    function ikeAddPendingSVG(element, handler) {
        if (!readyStateCompleteListeners.has(ikeRunPendingSVG)) {
            ikePendingSVG.splice(0);
            addReadyStateCompleteListener(ikeRunPendingSVG);
        }
        ikePendingSVG.push([element, handler]);
    }
"""),
    ("svg-sizes-root", """\
                                const svgBounds = root.getBoundingClientRect();
""", """\
                                const svgBounds = ikeSVGRect(root);
"""),
    ("svg-sizes-element", """\
                                const {width, height} =
                                    element.getBoundingClientRect();
""", """\
                                const {width, height} = ikeSVGRect(element);
"""),
    ("svg-sizes-pending", """\
                            addReadyStateCompleteListener(handleSVGElement);
""", """\
                            ikeAddPendingSVG(element, handleSVGElement);
"""),
    ("svg-sizes-discover", """\
        function discoverNodes(node) {
            getInlineStyleElements(node).forEach((el) => {
                if (discoveredNodes.has(el)) {
                    return;
                }
                discoveredNodes.add(el);
                elementStyleDidChange(el);
            });
""", """\
        function discoverNodes(node, ikeElements = getInlineStyleElements(node)) {
            ikeElements.forEach((el) => {
                if (discoveredNodes.has(el)) {
                    return;
                }
                discoveredNodes.add(el);
                elementStyleDidChange(el);
            });
"""),
    ("svg-sizes-additions", """\
            onMinorMutations: (_root, {additions}) => {
                additions.forEach((added) => discoverNodes(added));
                variablesStore.matchVariablesAndDependents();
            },
""", """\
            onMinorMutations: (_root, {additions}) => {
                const ikeLists = [];
                additions.forEach((added) =>
                    ikeLists.push([added, getInlineStyleElements(added)])
                );
                ikeWithSVGRects(
                    ikeLists.flatMap((item) => item[1]),
                    () => ikeLists.forEach(([added, elements]) =>
                        discoverNodes(added, elements)
                    )
                );
                variablesStore.matchVariablesAndDependents();
            },
"""),
    ("svg-sizes-attributes", """\
            const handledTargets = new Set();
            mutations.forEach((m) => {
                const target = m.target;
                if (handledTargets.has(target)) {
                    return;
                }
                if (INLINE_STYLE_ATTRS.includes(m.attributeName)) {
                    handledTargets.add(target);
                    elementStyleDidChange(target);
                }
            });
""", """\
            const handledTargets = new Set();
            ikeWithSVGRects(
                mutations.map((m) => m.target),
                () => mutations.forEach((m) => {
                const target = m.target;
                if (handledTargets.has(target)) {
                    return;
                }
                if (INLINE_STYLE_ATTRS.includes(m.attributeName)) {
                    handledTargets.add(target);
                    elementStyleDidChange(target);
                }
            }));
"""),
    ("svg-sizes-start", """\
        inlineStyleElements.forEach((el) =>
            overrideInlineStyle(
                el,
                theme,
                ignoredInlineSelectors,
                ignoredImageAnalysisSelectors
            )
        );
        handleAdoptedStyleSheets(document);
""", """\
        ikeWithSVGRects(inlineStyleElements, () =>
            inlineStyleElements.forEach((el) =>
            overrideInlineStyle(
                el,
                theme,
                ignoredInlineSelectors,
                ignoredImageAnalysisSelectors
            )
        ));
        handleAdoptedStyleSheets(document);
"""),
    ("svg-sizes-shadow", """\
                if (inlineStyleElements.length > 0) {
                    forEach(inlineStyleElements, (el) =>
                        overrideInlineStyle(
                            el,
                            theme,
                            ignoredInlineSelectors,
                            ignoredImageAnalysisSelectors
                        )
                    );
                }
""", """\
                if (inlineStyleElements.length > 0) {
                    ikeWithSVGRects(inlineStyleElements, () =>
                    forEach(inlineStyleElements, (el) =>
                        overrideInlineStyle(
                            el,
                            theme,
                            ignoredInlineSelectors,
                            ignoredImageAnalysisSelectors
                        )
                    ));
                }
"""),
    # Every colour Dark Reader changes is written as
    # var(--darkreader-<kind>-<hex>, <colour>), and the same variable was also
    # set on :root. Setting a new variable on :root makes the browser style the
    # whole page again (every element, every shadow tree), each time the page
    # shows a colour it had not shown before. The variable is now set on :root
    # only when something reads it without that fallback (the site's fix in
    # Dark Reader's list names it) or when its colour is not the one already
    # written as fallback; otherwise the fallback is the same colour.
    ("color-variables", """\
    function registerVariablesSheet(sheet) {
""", """\
    // I.K.E.: is a colour variable needed on :root?
    const ikeColorFallbacks = new Map();
    const ikeColorsOnRoot = new Set();
    let ikeFixCSS = null;
    let ikeFixColors = new Set();
    function ikeColorOnRoot(variable, value) {
        const css = (fixes && fixes.css) || "";
        if (css !== ikeFixCSS) {
            ikeFixCSS = css;
            ikeFixColors = new Set(
                css.match(/--darkreader-(?:background|text|border)-[0-9a-f]+/g)
            );
        }
        if (!ikeColorsOnRoot.has(variable)) {
            const fallback = ikeColorFallbacks.get(variable);
            if (fallback === undefined) {
                ikeColorFallbacks.set(variable, value);
            }
            if (
                !ikeFixColors.has(variable) &&
                (fallback === undefined || fallback === value)
            ) {
                return false;
            }
            ikeColorsOnRoot.add(variable);
        }
        return true;
    }
    function registerVariablesSheet(sheet) {
"""),
    ("color-variables-sheet", """\
                    const {variable, value} = registered[type];
                    rule.style.setProperty(variable, value);
""", """\
                    const {variable, value} = registered[type];
                    if (ikeColorOnRoot(variable, value)) {
                        rule.style.setProperty(variable, value);
                    }
"""),
    ("color-variables-register", """\
        getVariablesRule()?.style.setProperty(variable, value);
""", """\
        if (ikeColorOnRoot(variable, value)) {
            getVariablesRule()?.style.setProperty(variable, value);
        }
"""),
]


def apply_patches(engine):
    """I.K.E.'s changes (PATCHES), each found exactly once, in the engine's own line ends."""
    nl = "\r\n" if "\r\n" in engine else "\n"
    for name, old, new in PATCHES:
        old, new = old.replace("\n", nl), new.replace("\n", nl)
        n = engine.count(old)
        if n != 1:
            raise SystemExit("patch %r: the text it changes was found %d times instead of once" % (name, n))
        engine = engine.replace(old, new)
    return engine

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
    engine = apply_patches(PROXY_BLOCK.sub(lambda _m: PROXY_EVENT, lib))
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
