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
newest lists on GitHub. The owner's rules for every update (2026-11-24):

1. The proxy change (PROXY_BLOCK, PROXY_EVENT with the session's token) is not
   a speed patch: when it cannot be made the build STOPS (without it Google's
   sites break, or a page could start the proxy itself).
2. I.K.E.'s speed patches (PATCHES) are kept whenever they still fit. One whose
   text is not found exactly once is LEFT OUT with the rest of its family and
   the families that need it (PATCH_NEEDS); the build goes on, prints it and
   records it in darkreader-data.json ("ike_build"), so the daily report, the
   candidate's CHANGELOG line and the signing notice show it.
3. Links: every absolute link in darkreader.js and darkreader-proxy.js is
   either allowed (LINKS_ALLOWED, each with its reason, or a bare scheme such
   as "https://" that code compares with), or removed: from a comment, or from
   a string whose link is of a denied kind (LINK_DENY: donation, social,
   news, analytics, advertising), the string becoming "" (a template literal
   loses only the link). An unknown link in a string, or a denied one that the
   code compares with, STOPS the build: a person decides.
4. Network calls: the calls of fetch, XMLHttpRequest, sendBeacon, WebSocket,
   EventSource and importScripts are counted (NETWORK_CALLS); a new kind or a
   changed count STOPS the build.
5. The API I.K.E.'s Dark Reader panel uses (PANEL_API: enable(theme, fixes),
   disable, setFetchMethod and the theme's fields) must still be there, or the
   build STOPS.
6. The site fixes (darkreader-data.json) are data for Dark Reader: CSS put in
   a style element, selectors and flags. Nothing in them can be a script, and
   anything that looks like one STOPS the build (DATA_SCRIPT_MARKS).
7. What is written must still read as the same script: I.K.E.'s own reader of
   the text (lex) finds the same code before and after the links are removed,
   and node --check, when Node.js is there, accepts it whenever it accepts
   Dark Reader's own engine.

A build that stops writes nothing: the Dark Reader in use stays as it is, and
the daily report says why ("builder refused").
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "ike" / "resources"


def _darklists():
    """ike/darklists.py of this checkout, read by its path (no package, no Qt):
    the browser reads and checks the lists it fetches itself with the very
    same functions (1.1.27)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_darklists", ROOT / "ike" / "darklists.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_DL = _darklists()
DATA_SCRIPT_MARKS, data_problems = _DL.DATA_SCRIPT_MARKS, _DL.data_problems
FIX_COMMANDS, HINT_COMMANDS, COMMAND_LINE = _DL.FIX_COMMANDS, _DL.HINT_COMMANDS, _DL.COMMAND_LINE
parse_array, parse_blocks, fix_value, hint_value = _DL.parse_array, _DL.parse_blocks, _DL.fix_value, _DL.hint_value

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
    # Only changes with a measured gain are kept (2026-11-21, CPU time of the
    # page's renderer, gain larger than the spread in two runs; numbers in
    # docs/review/tests-and-performance.md, "1.1.21, Dark Reader: only the
    # measured changes"):
    # - measured against all 53 changes of 1.1.20: color-variables,
    #   style-groups, shadow-texts, shadow-host-walk;
    # - measured when added back to a build with only those four: dark-copy
    #   with shadow-styles-once (200 shadow roots, -24 / -18 %),
    #   declarations-modifiable (2,000 CSS rules, -6 / -9 %) and
    #   variables-none (same page, -7 / -7 %);
    # - measured when added back to a build with those eight: style-moves
    #   (repeated SVG icons, -12 / -13 %).
    #   Against the full build the gain of these five was hidden in its
    #   larger spread.
    # Removed, no gain larger than the spread in two runs, so the engine stays
    # closer to Dark Reader's own and a new engine has fewer texts to match:
    # svg-sizes (above the spread in 1 of 3 runs), adopted-once and
    # adopted-vars-first (also when added back), one-text (also when added
    # back) and var-rule-same-text (which needs it; its code path was never
    # reached), image-selectors, inline-style-key.

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
    # Identical style elements (same text, media, type and title, in the same
    # document or shadow root; many pages repeat an SVG icon with its own
    # <style>) each got their own copy from Dark Reader, so every element of
    # the page was matched against all those copies. All the originals give
    # the same declarations and all the copies the same changed ones; a copy
    # always comes right after its original, so in the cascade the copy after
    # the LAST original is the one that wins over the others and over any
    # other rule placed between them. Only that copy is kept. When the last
    # original changes (added, removed or moved by the page), the copy goes
    # after the new last one before anything is drawn; an element whose text
    # or style sheet the page changes leaves its group and gets its own copy
    # again, as Dark Reader does.
    ("style-groups", """\
    function manageStyle(element, {update, loadingStart, loadingEnd}) {
""", """\
    // I.K.E.: groups of identical style elements share one copy
    const ikeStyleGroups = new WeakMap();
    // I.K.E.: the dark copy of a group's rules, by theme and rules (1.1.19)
    const ikeDarkTexts = new Map();
    let ikeStyleEpoch = 0;
    let ikeStyleEpochQueued = false;
    function ikeLastStyle(group) {
        if (group.ikeLast !== undefined && group.ikeEpoch === ikeStyleEpoch) {
            return group.ikeLast;
        }
        let last = null;
        group.forEach((member) => {
            const el = member.element;
            if (!el.isConnected || el.getRootNode() !== group.ikeRoot) {
                return;
            }
            if (
                !last ||
                last.element.compareDocumentPosition(el) &
                    Node.DOCUMENT_POSITION_FOLLOWING
            ) {
                last = member;
            }
        });
        group.ikeLast = last;
        group.ikeEpoch = ikeStyleEpoch;
        if (!ikeStyleEpochQueued) {
            ikeStyleEpochQueued = true;
            queueMicrotask(() => {
                ikeStyleEpochQueued = false;
                ikeStyleEpoch++;
            });
        }
        return last;
    }
    function ikeSettleStyleGroup(group) {
        group.ikeLast = undefined;
        const last = ikeLastStyle(group);
        if (last && last.rendered() && !last.hasCopy()) {
            last.uncover();
        }
    }
    function ikeCheckStyleGroups(root) {
        const groups = ikeStyleGroups.get(root);
        if (groups) {
            groups.forEach((group) => ikeSettleStyleGroup(group));
        }
    }
    function manageStyle(element, {update, loadingStart, loadingEnd}) {
"""),
    ("style-groups-member", """\
        let isOverrideEmpty = true;
        const isAsyncCancelled = () => cancelAsyncOperations;
""", """\
        let isOverrideEmpty = true;
        const isAsyncCancelled = () => cancelAsyncOperations;
        // I.K.E.: this element in its group of identical style elements
        let ikeGroup = null;
        let ikeApplied = null;
        let ikeCovered = false;
        let ikeRenderArgs = null;
        const ikeMember = {
            element,
            rendered: () => ikeRenderArgs !== null,
            hasCopy: () => !ikeCovered && Boolean(syncStyle && syncStyle.parentNode),
            cover: () => ikeCover(),
            uncover: () => ikeUncover()
        };
        function ikeJoinGroup() {
            if (
                inMode !== "next" ||
                !(
                    element instanceof HTMLStyleElement ||
                    element instanceof SVGStyleElement
                ) ||
                !element.isConnected ||
                containsCSSImport()
            ) {
                return;
            }
            // the rules the element really has: a style element filled
            // through the CSSOM (CSS-in-JS) has other rules than its text
            let ikeRules = "";
            try {
                const rules = element.sheet.cssRules;
                for (let i = 0, len = rules.length; i < len; i++) {
                    if (rules[i] instanceof CSSImportRule) {
                        return;
                    }
                    ikeRules += rules[i].cssText + "\\n";
                }
            } catch (err) {
                return;
            }
            const root = element.getRootNode();
            let groups = ikeStyleGroups.get(root);
            if (!groups) {
                groups = new Map();
                ikeStyleGroups.set(root, groups);
            }
            const key = [
                element.media,
                element.getAttribute("type"),
                element.getAttribute("title"),
                element.textContent,
                ikeRules
            ].join("\\u0000");
            let group = groups.get(key);
            if (!group) {
                group = new Set();
                group.ikeRoot = root;
                group.ikeKey = key;
                group.ikeGroups = groups;
                groups.set(key, group);
            }
            group.add(ikeMember);
            group.ikeLast = undefined;
            ikeGroup = group;
        }
        function ikeLeaveGroup(later) {
            const group = ikeGroup;
            if (!group) {
                return;
            }
            ikeGroup = null;
            group.delete(ikeMember);
            group.ikeLast = undefined;
            if (ikeCovered) {
                ikeCovered = false;
                forceRenderStyle = true;
            }
            if (group.size === 0) {
                group.ikeGroups.delete(group.ikeKey);
            } else if (later) {
                queueMicrotask(() => ikeSettleStyleGroup(group));
            } else {
                ikeSettleStyleGroup(group);
            }
        }
        function ikeCover() {
            ikeCovered = true;
            if (syncStylePositionWatcher) {
                syncStylePositionWatcher.stop();
                syncStylePositionWatcher = null;
            }
            removeNode(syncStyle);
            syncStyle = null;
            isOverrideEmpty = true;
        }
        function ikeUncover() {
            if (ikeRenderArgs) {
                forceRenderStyle = true;
                render(...ikeRenderArgs);
            }
        }
        function ikeGroupCovers() {
            if (
                !element.isConnected ||
                element.getRootNode() !== ikeGroup.ikeRoot
            ) {
                ikeLeaveGroup(false);
                return false;
            }
            const last = ikeLastStyle(ikeGroup);
            if (last !== ikeMember) {
                ikeCover();
                if (last && last.rendered() && !last.hasCopy()) {
                    last.uncover();
                }
                return true;
            }
            if (ikeCovered) {
                ikeCovered = false;
                forceRenderStyle = true;
            }
            ikeGroup.forEach((member) => {
                if (member !== ikeMember && member.hasCopy()) {
                    member.cover();
                }
            });
            return false;
        }
        function ikeChanged() {
            ikeLeaveGroup(false);
            update();
        }
"""),
    ("style-groups-observer", """\
                const cssText = (element.textContent ?? "").trim();
                createOrUpdateCORSCopy(cssText, location.href).then(update);
            } else {
                update();
            }
""", """\
                ikeLeaveGroup(false);
                const cssText = (element.textContent ?? "").trim();
                createOrUpdateCORSCopy(cssText, location.href).then(update);
            } else {
                ikeChanged();
            }
"""),
    ("style-groups-render", """\
            cancelAsyncOperations = false;
            function removeCSSRulesFromSheet(sheet) {
""", """\
            cancelAsyncOperations = false;
            ikeRenderArgs = [theme, ignoreImageAnalysis];
            if (ikeGroup && ikeGroupCovers()) {
                return;
            }
            function removeCSSRulesFromSheet(sheet) {
"""),
    ("style-groups-async", """\
                    force,
                    isAsyncCancelled
                });
""", """\
                    force,
                    isAsyncCancelled: () => cancelAsyncOperations || ikeCovered
                });
"""),
    ("style-groups-sheet", """\
        const sheetChangeWatcher = createSheetWatcher(
            element,
            safeGetSheetRules,
            update,
            isAsyncCancelled
        );
""", """\
        const sheetChangeWatcher = createSheetWatcher(
            element,
            safeGetSheetRules,
            ikeChanged,
            isAsyncCancelled
        );
"""),
    ("style-groups-destroy", """\
        function destroy() {
            pause();
            corsCopies.delete(element);
""", """\
        function destroy() {
            ikeLeaveGroup(true);
            pause();
            corsCopies.delete(element);
"""),
    ("style-groups-restore", """\
        function restore() {
            if (!syncStyle) {
                return;
            }
""", """\
        function restore() {
            if (ikeGroup && element.getRootNode() !== ikeGroup.ikeRoot) {
                ikeChanged();
                return;
            }
            if (!syncStyle) {
                return;
            }
"""),
    # Every shadow root gets the same three style elements; the texts of the
    # first two (Dark Reader's inline-style rules and the site's fix with its
    # colours worked out) were built again for every root. They are built once
    # for a theme and a fix.
    ("shadow-texts", """\
    function createShadowStaticStyleOverridesInner(root) {
        const inlineStyle = createOrUpdateStyle("darkreader--inline", root);
        inlineStyle.textContent = getInlineOverrideStyle();
        root.insertBefore(inlineStyle, root.firstChild);
        const overrideStyle = createOrUpdateStyle("darkreader--override", root);
        overrideStyle.textContent =
            fixes && fixes.css ? replaceCSSTemplates(fixes.css) : "";
""", """\
    // I.K.E.: the same texts for every shadow root of a theme and a fix
    let ikeShadowTextCache = null;
    function ikeShadowTexts() {
        const css = fixes && fixes.css ? fixes.css : "";
        const cache = ikeShadowTextCache;
        if (cache && cache.theme === theme && cache.css === css) {
            return cache;
        }
        ikeShadowTextCache = {
            theme,
            css,
            inline: getInlineOverrideStyle(),
            override: css ? replaceCSSTemplates(css) : ""
        };
        return ikeShadowTextCache;
    }
    function createShadowStaticStyleOverridesInner(root) {
        const inlineStyle = createOrUpdateStyle("darkreader--inline", root);
        inlineStyle.textContent = ikeShadowTexts().inline;
        root.insertBefore(inlineStyle, root.firstChild);
        const overrideStyle = createOrUpdateStyle("darkreader--override", root);
        overrideStyle.textContent = ikeShadowTexts().override;
"""),
    ("style-groups-join", """\
        return {
            details,
            render,
            pause,
            destroy,
            watch,
            restore
        };
""", """\
        ikeJoinGroup();
        return {
            details,
            render,
            pause,
            destroy,
            watch,
            restore
        };
"""),
    ("style-groups-epoch", """\
            observer = new MutationObserver((mutations) => {
                if (isHugeMutation(mutations)) {
""", """\
            observer = new MutationObserver((mutations) => {
                ikeStyleEpoch++;
                if (isHugeMutation(mutations)) {
"""),
    ("style-groups-moves", """\
            handleStyleOperations(root, {
                createdStyles,
                removedStyles,
                movedStyles
            });
            const potentialHosts = new Set();
""", """\
            handleStyleOperations(root, {
                createdStyles,
                removedStyles,
                movedStyles
            });
            if (moves.size > 0) {
                ikeCheckStyleGroups(root);
            }
            const potentialHosts = new Set();
"""),
    ("style-groups-huge", """\
            handleStyleOperations(root, {
                createdStyles,
                removedStyles,
                movedStyles
            });
            deepObserve(root);
""", """\
            handleStyleOperations(root, {
                createdStyles,
                removedStyles,
                movedStyles
            });
            ikeCheckStyleGroups(root);
            deepObserve(root);
"""),
    # 1.1.19 (measured: docs/review/tests-and-performance.md). A style sheet
    # without CSS variables: the search for variables in it is skipped (every
    # variable and every var() has "--" in its text).
    ("variables-none", """\
        collectVarsFromCSSDeclarations(style) {
            iterateCSSDeclarations(style, (property, value) => {""", """\
        collectVarsFromCSSDeclarations(style) {
            // I.K.E.: no "--" in the text, no variable to collect
            if (!style.cssText.includes("--")) {
                return;
            }
            iterateCSSDeclarations(style, (property, value) => {"""),
    # The values of properties Dark Reader never changes (width, margin...) are
    # not read when a rule has no var(): getModifiableCSSDeclaration would
    # answer null for them. The guards below stop the build when a new engine
    # changes which properties it modifies, so the list never falls behind.
    ("declarations-modifiable", """\
    function iterateCSSDeclarations(style, iterate) {
        const cssText = style.cssText;
        if (cssText.includes("var(")) {""", """\
    // I.K.E.: the properties getModifiableCSSDeclaration can change
    function ikeMayModify(property) {
        return (
            property.includes("color") ||
            property === "fill" ||
            property === "stroke" ||
            property === "background-image" ||
            property === "list-style-image" ||
            property.includes("shadow") ||
            property.startsWith("--") ||
            bgPropsToCopy.includes(property)
        );
    }
    function iterateCSSDeclarations(style, iterate, ikeOnly = false) {
        const cssText = style.cssText;
        const ikeAll = !ikeOnly || cssText.includes("var(");
        if (cssText.includes("var(")) {"""),
    ("declarations-modifiable-skip", """\
        forEach(style, (property) => {
            const value = style.getPropertyValue(property).trim();
            if (!value) {
                return;
            }
            iterate(property, value);
        });
    }
    function handleEmptyShorthand(""", """\
        forEach(style, (property) => {
            if (!ikeAll && !ikeMayModify(property)) {
                return;
            }
            const value = style.getPropertyValue(property).trim();
            if (!value) {
                return;
            }
            iterate(property, value);
        });
    }
    function handleEmptyShorthand("""),
    ("declarations-modifiable-sheet", """\
                                if (mod) {
                                    modDecs.push(mod);
                                }
                            }
                        );""", """\
                                if (mod) {
                                    modDecs.push(mod);
                                }
                            },
                            true
                        );"""),
    ("declarations-modifiable-guard-colour", """\
        } else if (
            (property.includes("color") &&
                property !== "-webkit-print-color-adjust") ||
            property === "fill" ||
            property === "stroke" ||
            property === "stop-color"
        ) {""", """\
        } else if (
            (property.includes("color") &&
                property !== "-webkit-print-color-adjust") ||
            property === "fill" ||
            property === "stroke" ||
            property === "stop-color"
        ) {"""),
    ("declarations-modifiable-guard-image", """\
        } else if (
            property === "background-image" ||
            property === "list-style-image"
        ) {""", """\
        } else if (
            property === "background-image" ||
            property === "list-style-image"
        ) {"""),
    ("declarations-modifiable-guard-rest", """\
        } else if (property.includes("shadow")) {
            modifier = getShadowModifier(value);
        } else if (bgPropsToCopy.includes(property) && value !== "initial") {
            modifier = value;
        }""", """\
        } else if (property.includes("shadow")) {
            modifier = getShadowModifier(value);
        } else if (bgPropsToCopy.includes(property) && value !== "initial") {
            modifier = value;
        }"""),
    # A shadow root asked for its three dark styles a second time (by the
    # style watcher and by the inline-style watcher) when they are already
    # there, first and in order, with the same text: nothing to do.
    ("shadow-styles-once", """\
    function createShadowStaticStyleOverrides(root) {
        const delayed = root.firstChild === null;""", """\
    function createShadowStaticStyleOverrides(root) {
        // I.K.E.: already there, first, in order, with today's texts
        if (shadowRootsWithOverrides.has(root)) {
            const map = staticStyleMap.get(root);
            const a = map && map.get("darkreader--inline");
            const b = map && map.get("darkreader--override");
            const c = map && map.get("darkreader--invert");
            if (
                a && b && c &&
                root.firstChild === a &&
                a.nextSibling === b &&
                b.nextSibling === c &&
                a.textContent === ikeShadowTexts().inline &&
                b.textContent === ikeShadowTexts().override &&
                c.textContent === getInversionStyleValue()
            ) {
                return;
            }
        }
        const delayed = root.firstChild === null;"""),
    # The same style element in many shadow roots (web components, Lit): its
    # dark copy is made once, then given to each copy as text. Only for rules
    # without CSS variables, url() or anything Dark Reader finishes later, so
    # the copy depends on the rules and the theme alone; the key is the rules
    # the element really has (style-groups). Emptied before any rebuild.
    ("dark-copy-static", """\
        return {modifySheet, shouldRebuildStyle};""", """\
        return {modifySheet, shouldRebuildStyle, ikeStatic: () => ikeStatic};"""),
    ("dark-copy-static-flag", """\
        let hasNonLoadedLink = false;
        let wasRebuilt = false;""", """\
        let hasNonLoadedLink = false;
        let wasRebuilt = false;
        // I.K.E.: the last build had nothing asynchronous and no variables
        let ikeStatic = false;"""),
    ("dark-copy-static-set", """\
            buildStyleSheet();
        }
        return {modifySheet,""", """\
            buildStyleSheet();
            ikeStatic =
                !hasNonLoadedLink &&
                asyncDeclarationCounter === 0 &&
                varDeclarationCounter === 0;
        }
        return {modifySheet,"""),
    ("dark-copy-rebuild", """\
                syncStylePositionWatcher && syncStylePositionWatcher.stop();
                insertStyle();
                if (syncStyle.sheet == null) {
                    syncStyle.textContent = "";
                }""", """\
                syncStylePositionWatcher && syncStylePositionWatcher.stop();
                insertStyle();
                // I.K.E.: a copy given as text is emptied before a rebuild
                if (syncStyle.sheet == null || ikeApplied !== null) {
                    ikeApplied = null;
                    syncStyle.textContent = "";
                }"""),
    ("dark-copy-reuse", """\
            function buildOverrides() {
                const force = forceRenderStyle;
                forceRenderStyle = false;
                sheetModifier.modifySheet({""", """\
            function buildOverrides() {
                const force = forceRenderStyle;
                forceRenderStyle = false;
                // I.K.E.: the dark copy of the same rules, made once
                let ikeKey = null;
                if (
                    ikeGroup &&
                    !ikeGroup.ikeKey.includes("--") &&
                    !ikeGroup.ikeKey.includes("url(")
                ) {
                    ikeKey = getThemeKey$1(theme) + "\\u0000" + ikeGroup.ikeKey;
                    const text = ikeDarkTexts.get(ikeKey);
                    if (text !== undefined) {
                        if (
                            !force &&
                            ikeApplied === ikeKey &&
                            syncStyle &&
                            syncStyle.isConnected
                        ) {
                            return;
                        }
                        prepareOverridesSheet();
                        syncStyle.textContent = text;
                        ikeApplied = ikeKey;
                        isOverrideEmpty = text === "";
                        return;
                    }
                }
                ikeBuild(force);
                if (ikeKey && sheetModifier.ikeStatic() && syncStyle && syncStyle.sheet) {
                    let text = "";
                    const made = syncStyle.sheet.cssRules;
                    for (let i = 0; i < made.length; i++) {
                        text += made[i].cssText + "\\n";
                    }
                    if (ikeDarkTexts.size >= 256) {
                        ikeDarkTexts.clear();
                    }
                    ikeDarkTexts.set(ikeKey, text);
                }
            }
            function ikeBuild(force) {
                sheetModifier.modifySheet({"""),
    # 1.1.23 (the owner's decision of 2026-11-22): the colours of selected text
    # are written as colours. Dark Reader writes every colour as
    # var(--darkreader-<kind>-<hex>, <colour>), its "::selection" rule too; a
    # "::selection" that reads a variable makes the browser work out the
    # selection style again for every element that sets a CSS variable of its
    # own, at every restyle (1,695 more style resolutions in one restyle of
    # Speedometer's Lit page). The colour itself is written when the variable
    # is not set on :root (color-variables): the var() then always gives its
    # fallback, which is that colour. Same colours on the screen; the text of
    # this one rule is the only difference (docs/review/tests-and-performance.md,
    # "1.1.23, the colours of selected text").
    ("selection-colours", """\
        ["::selection", "::-moz-selection"].forEach((selection) => {
            lines.push(`${selection} {`);
            lines.push(
                `    background-color: ${backgroundColorSelection} !important;`
            );
            lines.push(`    color: ${foregroundColorSelection} !important;`);
            lines.push("}");
        });
        return lines.join("\\n");
    }
""", """\
        ["::selection", "::-moz-selection"].forEach((selection) => {
            lines.push(`${selection} {`);
            lines.push(
                `    background-color: ${ikePlainColor(backgroundColorSelection)} !important;`
            );
            lines.push(`    color: ${ikePlainColor(foregroundColorSelection)} !important;`);
            lines.push("}");
        });
        return lines.join("\\n");
    }
    // I.K.E.: var(--darkreader-<kind>-<hex>, <colour>) as the colour itself
    function ikePlainColor(value) {
        const m =
            /^var\\((--darkreader-(?:background|text|border)-[0-9a-f]+), ([^()]+)\\)$/.exec(
                value
            );
        return m && !ikeColorOnRoot(m[1], m[2]) ? m[2] : value;
    }
"""),
]


# --- The speed patches: what each family needs (the owner's decision of 2026-11-24) ---
# A speed patch whose text is not found exactly once in a new engine is left
# out, and the build goes on without it. A patch is never left out alone: its
# family (the patch of that name and every "<name>-..." one) shares functions
# and state and works only as a whole, and a family that needs another one is
# left out with it. Checked in the code of the patches:
PATCH_NEEDS = {
    "shadow-host-walk": (),                        # one patch
    "style-moves": (),                             # -check calls ikeStyleSibling
    "color-variables": (),                         # -sheet and -register call ikeColorOnRoot
    "style-groups": (),                            # 13 patches around manageStyle: one mechanism
    "shadow-texts": (),                            # one patch
    "variables-none": (),                          # one patch
    "declarations-modifiable": (),                 # the three guards keep ikeMayModify right
    "shadow-styles-once": ("shadow-texts",),       # reads ikeShadowTexts()
    "dark-copy": ("style-groups",),                # reads ikeGroup, ikeApplied, ikeDarkTexts
    "selection-colours": ("color-variables",),     # calls ikeColorOnRoot
}


def patch_family(name):
    fams = [f for f in PATCH_NEEDS if name == f or name.startswith(f + "-")]
    if not fams:
        raise SystemExit("patch %r belongs to no family of PATCH_NEEDS" % name)
    return max(fams, key=len)


def apply_patches(engine):
    """I.K.E.'s speed patches (PATCHES), each found exactly once, in the engine's own line ends.
    Returns (engine, left out): a family whose text is not found exactly once is left out with the
    families that need it, and the others are made again from the engine as it came (left out:
    [{"family", "patches", "reason"}], in the order of PATCHES)."""
    nl = "\r\n" if "\r\n" in engine else "\n"
    dropped = {}
    while True:
        out, failed = engine, None
        for name, old, new in PATCHES:
            if patch_family(name) in dropped:
                continue
            old, new = old.replace("\n", nl), new.replace("\n", nl)
            n = out.count(old)
            if n != 1:
                failed = (patch_family(name), "patch %r: the text it changes was found %d times instead of once"
                          % (name, n))
                break
            out = out.replace(old, new)
        if failed is None:
            break
        dropped[failed[0]] = failed[1]
        more = True
        while more:
            more = False
            for fam, needs in PATCH_NEEDS.items():
                gone = [x for x in needs if x in dropped]
                if fam not in dropped and gone:
                    dropped[fam] = "it needs %s, left out" % ", ".join(repr(x) for x in gone)
                    more = True
    order = []
    for name, _old, _new in PATCHES:
        fam = patch_family(name)
        if fam in dropped and fam not in order:
            order.append(fam)
    return out, [{"family": fam, "patches": [n for n, _o, _w in PATCHES if patch_family(n) == fam],
                  "reason": dropped[fam]} for fam in order]


# --- Reading the script: comments, strings, template literals, code ------------

_PUNCTS = (">>>=", "...", "===", "!==", "**=", "<<=", ">>=", ">>>", "&&=", "||=", "??=", "=>", "==", "!=",
           "<=", ">=", "&&", "||", "??", "?.", "++", "--", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
           "**", "<<", ">>")
_REGEX_AFTER = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do",
                "else", "yield", "await"}
_IDENT = re.compile(r"[A-Za-z0-9_$\u0080-\uffff]+")
_NUMBER = re.compile(r"(?:0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?|\.\d[\d_]*(?:[eE][+-]?\d+)?)n?")
_SPACE = " \t\r\n\u00a0\ufeff\u2028\u2029\v\f"


def lex(text):
    """The script's tokens, [(kind, start, end)]; kind: comment, string, template (the text of a template
    literal between its ` and ${ / } / `), regex, ident, number, punct. Raises ValueError on a text it
    cannot read (an unclosed comment, string, template or regular expression)."""
    toks, i, n = [], 0, len(text)
    depth, open_tpl = 0, []
    last = None                                # the last token that is not a comment

    def template(i):
        """The text of a template literal from i (after ` or the } of a ${}): returns where it goes on."""
        j = i
        while j < n:
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                toks.append(("template", i, j))
                toks.append(("punct", j, j + 1))
                return j + 1, False
            if c == "$" and text.startswith("${", j):
                toks.append(("template", i, j))
                toks.append(("punct", j, j + 2))
                return j + 2, True
            j += 1
        raise ValueError("a template literal is not closed (from offset %d)" % i)

    while i < n:
        c = text[i]
        if c in _SPACE:
            i += 1
            continue
        if text.startswith("//", i):
            j = i + 2
            while j < n and text[j] not in "\r\n\u2028\u2029":
                j += 1
            toks.append(("comment", i, j))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError("a comment is not closed (from offset %d)" % i)
            toks.append(("comment", i, j + 2))
            i = j + 2
            continue
        if c in "'\"":
            j = i + 1
            while True:
                if j >= n or text[j] in "\r\n":
                    raise ValueError("a string is not closed (from offset %d)" % i)
                if text[j] == "\\":
                    j += 3 if text.startswith("\r\n", j + 1) else 2
                    continue
                if text[j] == c:
                    break
                j += 1
            toks.append(("string", i, j + 1))
            last = toks[-1]
            i = j + 1
            continue
        if c == "`":
            toks.append(("punct", i, i + 1))
            i, inside = template(i + 1)
            if inside:
                open_tpl.append(depth)
            last = toks[-1]
            continue
        if c == "}" and open_tpl and open_tpl[-1] == depth:
            open_tpl.pop()
            toks.append(("punct", i, i + 1))
            i, inside = template(i + 1)
            if inside:
                open_tpl.append(depth)
            last = toks[-1]
            continue
        if c == "/":
            lt = text[last[1]:last[2]] if last else ""
            regex = (last is None or (last[0] == "punct" and lt not in (")", "]", "`"))
                     or (last[0] == "ident" and lt in _REGEX_AFTER))
            if regex:
                j, cls = i + 1, False
                while True:
                    if j >= n or text[j] in "\r\n":
                        raise ValueError("a regular expression is not closed (from offset %d)" % i)
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "[":
                        cls = True
                    elif text[j] == "]":
                        cls = False
                    elif text[j] == "/" and not cls:
                        break
                    j += 1
                m = _IDENT.match(text, j + 1)
                end = m.end() if m else j + 1
                toks.append(("regex", i, end))
                last = toks[-1]
                i = end
                continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUMBER.match(text, i)
            toks.append(("number", i, m.end()))
            last = toks[-1]
            i = m.end()
            continue
        m = _IDENT.match(text, i)
        if m:
            toks.append(("ident", i, m.end()))
            last = toks[-1]
            i = m.end()
            continue
        if c == "\\":
            raise ValueError("an escape outside a string (offset %d)" % i)
        p = next((p for p in _PUNCTS if text.startswith(p, i)), c)
        if p == "{":
            depth += 1
        elif p == "}":
            depth -= 1
        toks.append(("punct", i, i + len(p)))
        last = toks[-1]
        i += len(p)
    if open_tpl:
        raise ValueError("a template literal's ${ } is not closed")
    return toks


def code_shape(text):
    """The script as code: every token but comments, strings and template texts by its own text, those by
    their kind only. Removing a link from a comment or a string must leave it the same."""
    return [(k, text[s:e]) if k not in ("comment", "string", "template") else (k, "") for k, s, e in lex(text)]


def code_tokens(text):
    """(kind, text) of every token but the comments."""
    return [(k, text[s:e]) for k, s, e in lex(text) if k != "comment"]


# --- Links (the owner's decision of 2026-11-24) ----------------------------------
# Dark Reader's code may carry links to anything (its site, donations, news,
# social networks). Only what Dark Reader needs to work, or the notice its
# licence requires, stays. Each allowed link, with why (none is ever contacted):
LINKS_ALLOWED = {
    "https://darkreader.org": "Dark Reader's name and site in its banner and in I.K.E.'s notes (the MIT "
                              "licence's notice: text, never contacted)",
    "https://darkreader.org/": "the same, in the engine's header comment",
    "https://github.com/darkreader/darkreader/blob/main/LICENSE": "the MIT licence named in the CSS that "
                                                                   "Dark Reader exports (the licence's notice: text)",
    "https://fonts.googleapis.com/": "compared with a style sheet's address (startsWith): Google Fonts' sheets "
                                     "are handled apart; this string is never fetched",
    "http://www.w3.org/2000/svg": "the SVG namespace: a name for createElementNS, never contacted",
    "http://www.w3.org/1999/xlink": "the XLink namespace: a name, never contacted",
    "http://www.w3.org/1999/xhtml": "the XHTML namespace: a name, never contacted",
}
# A scheme with nothing after "://" ("https://", "moz-extension://") is kept: the
# code compares addresses with it (startsWith), it links nowhere.
# The kinds of link that are removed: (kind, sites, words of the path). A site
# is "domain" (and its subdomains), "domain/path" (that path and below) or
# "label." (any host that starts with it).
LINK_DENY = (
    ("donation", ("patreon.com", "opencollective.com", "paypal.com", "paypal.me", "liberapay.com", "ko-fi.com",
                  "buymeacoffee.com", "github.com/sponsors", "donate.", "donorbox.org", "flattr.com"),
     ("donate", "donation", "donations", "sponsor", "sponsors", "support-us", "backers")),
    ("social", ("twitter.com", "x.com", "facebook.com", "fb.com", "instagram.com", "linkedin.com", "reddit.com",
                "youtube.com/@", "youtube.com/channel", "youtube.com/c/", "youtube.com/user", "youtu.be",
                "discord.gg", "discord.com", "discordapp.com", "t.me", "telegram.me", "telegram.org",
                "mastodon.social", "mastodon.", "tiktok.com", "threads.net", "bsky.app", "vk.com"), ()),
    ("news", ("medium.com", "substack.com", "blogspot.com", "blog.", "news."),
     ("news", "blog", "whats-new", "whatsnew", "what-s-new", "changelog", "release-notes")),
    ("analytics", ("google-analytics.com", "googletagmanager.com", "sentry.io", "segment.io", "segment.com",
                   "mixpanel.com", "amplitude.com", "hotjar.com", "plausible.io", "posthog.com", "bugsnag.com",
                   "nr-data.net", "datadoghq.com", "clarity.ms", "matomo.cloud", "analytics.", "telemetry.",
                   "stats.", "metrics.", "tracking."), ("analytics", "telemetry")),
    ("advertising", ("doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
                     "amazon-adsystem.com", "carbonads.net", "buysellads.com", "ads."), ()),
)
_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'`<>(){}\[\]\\|^]*")
_BARE = re.compile(r"(?<![\w.@/-])(?:www\.)?(?:%s)(?:/[^\s\"'`<>(){}\[\]\\|^]*)" % "|".join(
    re.escape(site) for _kind, sites, _w in LINK_DENY for site in sites if not site.endswith(".")))
_COMPARE = {"===", "!==", "==", "!=", "case", "in"}
_COMPARE_CALLS = {"startsWith", "endsWith", "includes", "indexOf", "lastIndexOf", "match", "search", "test",
                  "replace", "replaceAll", "split", "has", "get"}


def _strip(url):
    if "*/" in url:                                       # the end of a comment is not part of a link
        url = url[:url.index("*/")]
    while url and url[-1] in ".,;:!?*":
        url = url[:-1]
    return url


def link_kind(url):
    """The kind of LINK_DENY of a link (with or without its scheme), or ""."""
    rest = url.split("://", 1)[1] if "://" in url else url
    host, _, path = rest.partition("/")
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].lower()
    path = "/" + path.split("?", 1)[0].split("#", 1)[0].lower()
    for kind, sites, words in LINK_DENY:
        for site in sites:
            if site.endswith("."):
                if host.startswith(site) or ("." + site) in ("." + host):
                    return kind
                continue
            domain, _, under = site.partition("/")
            if host == domain or host.endswith("." + domain):
                if not under or path.startswith("/" + under):
                    return kind
        if any(seg in words for seg in path.split("/")):
            return kind
    return ""


def _is_compared(code, i):
    """Is the string code[i] compared with or looked up (removing it would change what the code does)?"""
    prev = code[i - 1][1] if i > 0 else ""
    nxt = code[i + 1][1] if i + 1 < len(code) else ""
    if prev in _COMPARE or nxt in _COMPARE:
        return True
    if prev == "[" and i >= 2 and (code[i - 2][0] in ("ident", "string") or code[i - 2][1] in (")", "]")):
        return True                                       # a lookup, obj["..."]
    if nxt == ":" and prev in ("{", ","):
        return True                                       # a key of an object
    return prev == "(" and i >= 3 and code[i - 2][0] == "ident" and code[i - 2][1] in _COMPARE_CALLS \
        and code[i - 3][1] in (".", "?.")


def scan_links(text):
    """Every absolute link of a script: [{"where" (comment, string, template), "url", "start", "end" (of the
    link, or of the whole string for a string), "line", "verdict" (keep, remove, stop), "why", "kind"}]."""
    toks = lex(text)
    code = [(k, text[s:e], s, e) for k, s, e in toks if k != "comment"]
    at = {s: n for n, (_k, _t, s, _e) in enumerate(code)}
    found, spans = [], []
    for kind, s, e in toks:
        if kind not in ("comment", "string", "template"):
            continue
        if kind == "string":
            body = re.sub(r"\\x2[fF]|\\u002[fF]", "/", text[s + 1:e - 1].replace("\\/", "/"))
        else:
            body = text[s:e]
        hits = [(m.start(), m.end(), _strip(m.group())) for m in _URL.finditer(body)]
        hits += [(m.start(), m.end(), _strip(m.group())) for m in _BARE.finditer(body)
                 if not any(a <= m.start() < b for a, b, _u in hits)]
        for a, b, url in hits:
            item = {"where": kind, "url": url, "kind": ""}
            if kind == "string":
                item["start"], item["end"] = s, e
            else:
                item["start"], item["end"] = s + a, s + a + len(url)
            item["line"] = text.count("\n", 0, item["start"]) + 1
            spans.append((s, e))
            host = url.split("://", 1)[1] if "://" in url else url
            if "://" in url and not host:
                item.update(verdict="keep", why="a scheme the code compares with, no link")
            elif url in LINKS_ALLOWED:
                item.update(verdict="keep", why=LINKS_ALLOWED[url])
            elif kind == "comment":
                item.update(verdict="remove", kind=link_kind(url) or "unknown", why="in a comment")
            elif not link_kind(url):
                item.update(verdict="stop", why="an unknown link in a %s: not in LINKS_ALLOWED and of no kind "
                                                "of LINK_DENY" % ("string" if kind == "string" else
                                                                  "template literal"))
            elif kind == "string" and _is_compared(code, at[s]):
                item.update(verdict="stop", kind=link_kind(url),
                            why="a %s link the code compares with: removing it would change what the code does"
                                % link_kind(url))
            else:
                item.update(verdict="remove", kind=link_kind(url), why="a %s link" % link_kind(url))
            found.append(item)
    # every link of the text is in a comment or a string the scan read
    for m in _URL.finditer(text):
        if not any(a <= m.start() < b for a, b in spans):
            found.append({"where": "code", "url": _strip(m.group()), "start": m.start(), "end": m.end(),
                          "line": text.count("\n", 0, m.start()) + 1, "verdict": "stop", "kind": "",
                          "why": "a link outside the comments and strings the scan read"})
    return found


def scrub_links(text, name):
    """The script without the links that must go (scan_links). Returns (text, removed), removed:
    [{"file", "line", "where", "kind", "host"}]; stops the build on a link a person must judge."""
    found = scan_links(text)
    stops = [f for f in found if f["verdict"] == "stop"]
    if stops:
        raise SystemExit("links: %s: %s" % (name, "; ".join("line %d, %s: %s" % (f["line"], f["url"][:120], f["why"])
                                                              for f in stops[:5])))
    gone = [f for f in found if f["verdict"] == "remove"]
    out = text
    for f in sorted({(f["start"], f["end"], f["where"]): f for f in gone}.values(), key=lambda f: -f["start"]):
        if f["where"] == "string":
            q = text[f["start"]]
            out = out[:f["start"]] + q + q + out[f["end"]:]
        else:
            out = out[:f["start"]] + out[f["end"]:]
    if gone and code_shape(out) != code_shape(text):
        raise SystemExit("links: %s: removing the links would change the script's code" % name)
    removed = []
    for f in gone:
        host = (f["url"].split("://", 1)[1] if "://" in f["url"] else f["url"]).split("/", 1)[0]
        removed.append({"file": name, "line": f["line"], "where": f["where"], "kind": f["kind"], "host": host})
    return out, removed


# --- Network calls ---------------------------------------------------------------
# The calls that reach the network, counted in the code (not in comments or
# strings): the name called, as fetch(...) or new WebSocket(...). Dark Reader
# 4.9.135: fetch four times (a style sheet or an image the page uses, through
# I.K.E.'s setFetchMethod; window.DarkReader.Plugins.fetch; a data: address),
# nothing else. A new kind or another count stops the build: a person reads the
# new call first, then changes this.
NETWORK_KINDS = ("fetch", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts")
NETWORK_CALLS = {"darkreader.js": {"fetch": 4}, "darkreader-proxy.js": {}}


def network_calls(text):
    code = code_tokens(text)
    out = {}
    for i, (k, t) in enumerate(code[:-1]):
        if k == "ident" and t in NETWORK_KINDS and code[i + 1] == ("punct", "("):
            out[t] = out.get(t, 0) + 1
    return out


def check_network(text, name):
    calls, want = network_calls(text), NETWORK_CALLS[name]
    if calls != want:
        diff = ", ".join("%s %d -> %d" % (k, want.get(k, 0), calls.get(k, 0)) for k in NETWORK_KINDS
                         if want.get(k, 0) != calls.get(k, 0))
        raise SystemExit("network calls: %s: %s (a person reads the new calls, then changes NETWORK_CALLS)"
                         % (name, diff))


# --- The API I.K.E.'s Dark Reader panel uses ---------------------------------------
# ike/resources/darkmode.js calls DarkReader.enable(theme, fixes), disable() and
# setFetchMethod(); the panel's settings are fields of the theme.
PANEL_API = {
    "exports": ("enable", "disable", "setFetchMethod"),
    "theme": ("mode", "brightness", "contrast", "sepia", "grayscale", "useFont", "fontFamily", "textStroke",
              "darkSchemeBackgroundColor", "darkSchemeTextColor", "lightSchemeBackgroundColor",
              "lightSchemeTextColor", "scrollbarColor", "selectionColor"),
}


def api_problems(engine):
    """What of PANEL_API the engine no longer has ([] when all of it is there)."""
    code = code_tokens(engine)
    texts = [t for _k, t in code]
    missing = []
    for name in PANEL_API["exports"]:
        if not any(texts[i:i + 4] == ["exports", ".", name, "="] for i in range(len(texts) - 3)):
            missing.append("exports.%s" % name)
    at = next((i for i in range(len(texts) - 2) if texts[i:i + 3] == ["function", "enable", "("]), None)
    if at is None:
        missing.append("function enable(theme, fixes)")
    else:
        j, level, commas = at + 3, 0, 0
        while j < len(texts) and not (level == 0 and texts[j] == ")"):
            level += texts[j] in ("(", "[", "{")
            level -= texts[j] in (")", "]", "}")
            commas += level == 0 and texts[j] == ","
            j += 1
        if commas < 1:
            missing.append("enable(theme, fixes): its second parameter")
    at = next((i for i in range(len(texts) - 2) if texts[i:i + 3] == ["DEFAULT_THEME", "=", "{"]), None)
    keys, end = set(), at
    if at is None:
        missing.append("DEFAULT_THEME")
    else:
        j, level = at + 2, 0
        while j < len(texts):
            level += texts[j] in ("(", "[", "{")
            level -= texts[j] in (")", "]", "}")
            if level == 0:
                break
            if level == 1 and code[j][0] == "ident" and texts[j - 1] in ("{", ",") and texts[j + 1] in (":", ",", "}"):
                keys.add(texts[j])
            j += 1
        end = j
    for field in PANEL_API["theme"]:
        if field not in keys:
            missing.append("theme.%s (DEFAULT_THEME)" % field)
            continue
        used = any((texts[i - 1] in (".", "?.") and texts[i] == field) or
                   (code[i][0] == "string" and texts[i][1:-1] == field)
                   for i in range(1, len(texts)) if not at <= i <= end)
        if not used:
            missing.append("theme.%s (never read)" % field)
    return missing


# --- The site fixes: data, never a script ----------------------------------------
# A fix's "css" goes into a <style> element; "invert", "ignoreInlineStyle",
# "ignoreImageAnalysis" and "ignoreCSSUrl" are selectors (or flags); a detector
# hint's "target" and "match" are selectors. None of it runs as a script in
# Chromium. Addresses of a site's own pictures or fonts in its CSS are fine.
# DATA_SCRIPT_MARKS and data_problems: ike/darklists.py (1.1.27: the browser
# checks the lists it fetches itself the very same way)

# --- The parse check ------------------------------------------------------------

def node_parses(text):
    """True or False by node --check, None without Node.js."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory(prefix="ike-dr-") as d:
        path = Path(d) / "script.cjs"
        path.write_text(text, "utf-8")
        done = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, check=False)
    return done.returncode == 0


# FIX_COMMANDS, HINT_COMMANDS, parse_array, parse_blocks, fix_value,
# hint_value: ike/darklists.py (1.1.27: the browser reads the lists it fetches
# itself with the very same functions)

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


def build_engine(lib):
    """darkreader.js and darkreader-proxy.js from Dark Reader's engine (its text), with what the build
    left out or removed: (engine, proxy_js, notes); notes: {"speed_patches_dropped", "links_removed"}.
    Stops (SystemExit) as the rules at the top of this file say."""
    m = re.search(r"Dark Reader v([0-9.]+)", lib[:400])
    if not m:
        raise SystemExit("not Dark Reader's engine")
    version = m.group(1)
    found = PROXY_BLOCK.findall(lib)
    if len(found) != 1:
        raise SystemExit("the proxy injection of the engine was not found exactly once (%d)" % len(found))
    engine, dropped = apply_patches(PROXY_BLOCK.sub(lambda _m: PROXY_EVENT, lib))
    if engine.count(PROXY_EVENT) != 1:
        raise SystemExit("the proxy injection of the engine was not found exactly once after the patches")
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
    try:
        missing = api_problems(engine)
        if missing:
            raise SystemExit("Dark Reader's API that I.K.E.'s panel uses is not all there: %s"
                             % ", ".join(missing))
        engine, gone = scrub_links(engine, "darkreader.js")
        proxy_js, gone_proxy = scrub_links(proxy_js, "darkreader-proxy.js")
        check_network(engine, "darkreader.js")
        check_network(proxy_js, "darkreader-proxy.js")
    except ValueError as e:
        raise SystemExit("the engine could not be read as a script: %s" % e) from None
    # node --check, when it reads Dark Reader's own engine: then I.K.E.'s files must read too
    if node_parses(lib):
        for name, text in (("darkreader.js", engine), ("darkreader-proxy.js", proxy_js)):
            if not node_parses(text):
                raise SystemExit("%s does not parse (node --check) after I.K.E.'s changes" % name)
    return engine, proxy_js, {"speed_patches_dropped": dropped, "links_removed": gone + gone_proxy}


def build(lib_path, config, commit="", date=""):
    lib = Path(lib_path).read_bytes().decode("utf-8")      # its own line ends kept
    engine, proxy_js, notes = build_engine(lib)
    version = re.search(r"Dark Reader v([0-9.]+)", lib[:400]).group(1)
    cfg = Path(config)
    fixes = parse_blocks((cfg / "dynamic-theme-fixes.config").read_text("utf-8"), FIX_COMMANDS, fix_value)
    if not fixes or fixes[0]["url"][:1] != ["*"]:
        raise SystemExit("the site fixes do not start with the common fix")
    hints = parse_blocks((cfg / "detector-hints.config").read_text("utf-8"), HINT_COMMANDS, hint_value)
    dark = parse_array((cfg / "dark-sites.config").read_text("utf-8"))
    data = {"version": version, "lists_commit": commit, "lists_date": date,
            "fixes": fixes, "dark_sites": dark, "detector_hints": hints}
    problems = data_problems(data)
    if problems:
        raise SystemExit("the site fixes hold what could be a script: %s" % "; ".join(problems[:5]))
    # what the build left out or removed, for the daily report, the CHANGELOG line and the signing
    # notice (written only when there is something: an engine built whole has no such entry)
    notes = {k: v for k, v in notes.items() if v}
    if notes:
        data["ike_build"] = notes
    return engine, proxy_js, data


def summary(data):
    """The build's own lines: what it left out and removed."""
    notes = data.get("ike_build") or {}
    out = []
    for d in notes.get("speed_patches_dropped") or ():
        out.append("speed patch left out: %s (%s): %s" % (d["family"], ", ".join(d["patches"]), d["reason"]))
    for r in notes.get("links_removed") or ():
        out.append("link removed: %s line %d, %s, %s (%s)" % (r["file"], r["line"], r["where"], r["host"],
                                                              r["kind"]))
    return out


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
    for line in summary(data):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
