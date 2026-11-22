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
