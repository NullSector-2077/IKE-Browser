"""Page dark mode with Dark Reader as the Dark Reader extension uses it (1.1.4):
its lists (fixes for single sites, sites that are dark already, hints of a
site's own dark theme), its style-sheet proxy in the page's own world even
under a strict Content-Security-Policy, and its detector of a site's own dark
theme. All on this computer: local pages that behave as the hard cases do."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

# --- the lists ----------------------------------------------------------------


def test_address_patterns_as_dark_reader_matches_them():
    from ike.darkfixes import matches
    assert matches("https://example.com/a", "example.com")
    assert matches("https://www.example.com/a", "example.com")            # www. counts as the site
    assert not matches("https://sub.example.com/", "example.com")
    assert matches("https://sub.example.com/", "*.example.com")
    assert matches("https://example.com/", "example.*")
    assert matches("https://example.com/docs/x", "example.com/docs")
    assert not matches("https://example.com/blog", "example.com/docs")
    assert matches("https://example.com/docs", "example.com/docs$")
    assert not matches("https://example.com/docs/x", "example.com/docs$")
    assert matches("https://example.com:8080/", "example.com:8080")
    assert not matches("https://example.com:8081/", "example.com:8080")
    assert matches("https://anything.test/x", r"/anything\.test/")
    assert not matches("not an address", "example.com")


def test_the_lists_are_there_and_give_what_the_extension_gives():
    from ike import darkfixes
    d = darkfixes.data()
    assert d["version"] and len(d["fixes"]) > 1000 and d["fixes"][0]["url"] == ["*"]
    assert len(d["dark_sites"]) > 100 and len(d["detector_hints"]) > 50
    common = darkfixes.common_fix()
    # a site of the list gets the common fix and its own one
    site = next(f for f in d["fixes"][1:] if f.get("css") and not f["url"][0].startswith(("/", "^", "*"))
                and "/" not in f["url"][0] and "*" not in f["url"][0] and ":" not in f["url"][0])
    fix = darkfixes.fix_for("https://%s/" % site["url"][0])
    assert fix["css"].startswith(common["css"]) and site["css"] in fix["css"]
    # a site not in the list: the common fix alone
    assert darkfixes.fix_for("https://nothing-of-this.invalid/") == common
    # a site of the dark list, and one that is not
    dark = next(p for p in d["dark_sites"] if "*" not in p and "/" not in p and not p.startswith(("^", "$")))
    assert darkfixes.in_dark_list("https://%s/" % dark)
    assert not darkfixes.in_dark_list("https://nothing-of-this.invalid/")
    # the proxy is asked for with the extension's own event, never as an inline script
    from ike.config import RES_DIR
    engine = (RES_DIR / "darkreader.js").read_text("utf-8")
    assert "__darkreader__stylesheetProxy__arg" in engine and 'createOrUpdateScript("darkreader--proxy")' not in engine
    proxy = (RES_DIR / "darkreader-proxy.js").read_text("utf-8")
    assert "function injectProxy(" in proxy and "__darkreader__stylesheetProxy__arg" in proxy


def build_tool():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "build_darkreader", Path(__file__).resolve().parent.parent / "tools" / "build-darkreader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_api(tool):
    """What the build checks besides the patches (2026-11-24): the API I.K.E.'s panel uses
    (PANEL_API) and the engine's network calls (NETWORK_CALLS), as Dark Reader writes them."""
    fields = tool.PANEL_API["theme"]
    lines = ["    const DEFAULT_THEME = {"] + ["        %s: 0," % f for f in fields[:-1]] + \
        ["        %s: 0" % fields[-1], "    };", "    function enable(themeOptions = {}, fixes = null) {",
         "        const theme = {...DEFAULT_THEME, ...themeOptions};"] + \
        ["        use(theme.%s);" % f for f in fields] + ["    }"]
    for kind, n in tool.NETWORK_CALLS["darkreader.js"].items():
        lines += ["    %s(address);" % kind] * n
    lines += ["    exports.%s = %s;" % (name, name) for name in tool.PANEL_API["exports"]]
    return "\r\n".join(lines) + "\r\n"


def fake_engine(patches, skip=None):
    """An engine with the proxy injection, the text every I.K.E. patch changes and the API I.K.E.'s
    panel uses."""
    body = "".join(old for name, old, _new in patches if name != skip)
    return ("/**\r\n * Dark Reader v9.9.9\r\n */\r\n(function () {\r\n"
            "    function injectProxy(\r\n        a,\r\n        b\r\n    ) {\r\n        if (a) { b(); }\r\n    }\r\n"
            "    function other() {\r\n        {\r\n"
            "            const proxyScript = createOrUpdateScript(\"darkreader--proxy\");\r\n"
            "            proxyScript.append(`(${injectProxy})(${a}, ${b})`);\r\n"
            "            proxyScript.remove();\r\n        }\r\n    }\r\n"
            + fake_api(build_tool()) + body.replace("\n", "\r\n") + "})();\r\n")


def test_the_build_tool(tmp_path):
    """tools/build-darkreader.py: the proxy taken out of the engine and asked for
    by an event, I.K.E.'s changes made, the lists read; an engine it does not
    recognise is refused."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    patches = build_tool().PATCHES
    (tmp_path / "lib.js").write_bytes(fake_engine(patches).encode())
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "dynamic-theme-fixes.config").write_text(
        "*\n\nINVERT\n.logo\n\nCSS\nbody { color: red }\n\n====\n\nexample.com\n*.example.org\n\n"
        "IGNORE INLINE STYLE\n.x\n.y\n")
    (cfg / "dark-sites.config").write_text("dark.example\nnight.example/app\n")
    (cfg / "detector-hints.config").write_text("own.example\n\nTARGET\nhtml\n\nMATCH\n.dark\n\n"
                                               "====\n\nnever.example\n\nNO DARK THEME\n")
    out = tmp_path / "out"
    out.mkdir()
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "lib.js"),
                          "--config", str(cfg), "--out", str(out), "--commit", "abc"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    engine = (out / "darkreader.js").read_bytes().decode()
    assert "createOrUpdateScript" not in engine and "__darkreader__stylesheetProxy__arg__IKE_DR_TOKEN__" in engine
    assert "\r\n" in engine and "\n" not in engine.replace("\r\n", "")   # the engine's own line ends are kept
    for _name, old, new in patches:                           # every change made, in those line ends
        assert new.replace("\n", "\r\n") in engine
    proxy = (out / "darkreader-proxy.js").read_text()
    assert "function injectProxy(" in proxy and "if (a) { b(); }" in proxy and "other()" not in proxy
    data = json.loads((out / "darkreader-data.json").read_text())
    assert data["version"] == "9.9.9" and data["lists_commit"] == "abc"
    assert data["fixes"][0] == {"url": ["*"], "invert": [".logo"], "css": "body { color: red }"}
    assert data["fixes"][1] == {"url": ["example.com", "*.example.org"], "ignoreInlineStyle": [".x", ".y"]}
    assert data["dark_sites"] == ["dark.example", "night.example/app"]
    assert data["detector_hints"] == [{"url": ["own.example"], "target": "html", "match": [".dark"]},
                                      {"url": ["never.example"], "noDarkTheme": True}]
    (tmp_path / "bad.js").write_text("/**\n * Dark Reader v9.9.9\n */\nfunction injectProxy(\n    a\n) {\n}\n")
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "bad.js"),
                          "--config", str(cfg), "--out", str(out)], capture_output=True, text=True)
    assert run.returncode != 0 and "proxy injection" in (run.stderr + run.stdout)
    assert "ike_build" not in data                         # built whole: nothing left out, nothing removed
    # an engine where one of the texts of a speed patch is missing (the owner's decision of
    # 2026-11-24): never half-adapted, that patch's family is left out whole, with the families
    # that need it (shadow-styles-once reads ikeShadowTexts); every other patch is made, the build
    # goes on and says what it left out
    (tmp_path / "changed.js").write_bytes(fake_engine(patches, skip="shadow-texts").encode())
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "changed.js"),
                          "--config", str(cfg), "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "speed patch left out: shadow-texts (shadow-texts)" in run.stdout
    assert "speed patch left out: shadow-styles-once (shadow-styles-once): it needs 'shadow-texts'" in run.stdout
    engine = (tmp_path / "darkreader.js").read_bytes().decode()
    for name, old, new in patches:
        if name in ("shadow-texts", "shadow-styles-once"):
            assert new.replace("\n", "\r\n") not in engine, name
        else:
            assert engine.count(new.replace("\n", "\r\n")) == 1, name
    assert old_text(patches, "shadow-styles-once").replace("\n", "\r\n") in engine     # left as Dark Reader has it
    built = json.loads((tmp_path / "darkreader-data.json").read_text())["ike_build"]
    assert [d["family"] for d in built["speed_patches_dropped"]] == ["shadow-texts", "shadow-styles-once"]
    assert "found 0 times instead of once" in built["speed_patches_dropped"][0]["reason"]


def old_text(patches, name):
    return next(old for n, old, _new in patches if n == name)


def shipped_notes():
    """What the build left out or removed in the shipped Dark Reader (darkreader-data.json)."""
    from ike.config import RES_DIR
    return json.loads((RES_DIR / "darkreader-data.json").read_text("utf-8")).get("ike_build") or {}


def shipped_dropped(tool):
    """The names of the speed patches the shipped engine was built without."""
    fams = {d["family"] for d in shipped_notes().get("speed_patches_dropped") or ()}
    return {name for name, _o, _n in tool.PATCHES if tool.patch_family(name) in fams}


def test_the_engine_is_the_npm_engine_with_the_changes():
    """ike/resources/darkreader.js is what the build tool makes: undoing I.K.E.'s
    changes gives back Dark Reader's own text, and every change is in it once
    (but those of a speed patch the build had to leave out, darkreader-data.json
    "ike_build": none of their text is in it)."""
    from ike.config import RES_DIR
    tool = build_tool()
    engine = (RES_DIR / "darkreader.js").read_bytes().decode()
    dropped = shipped_dropped(tool)
    for name, old, new in tool.PATCHES:
        new, old = new.replace("\n", "\r\n"), old.replace("\n", "\r\n")
        if name in dropped:
            assert new == old or engine.count(new) == 0, name
            continue
        assert engine.count(new) == 1, name
        engine = engine.replace(new, old)
    assert engine.count(tool.PROXY_EVENT) == 1


# The families kept because their gain was measured (2026-11-21: four against
# all of 1.1.20's changes, five more when added back to a build with fewer
# changes), and what the families dropped for no measurable gain left in the
# engine (their names and their "I.K.E.:" notes): none of it may come back
# unmeasured. 1.1.23 (the owner's decision of 2026-11-22) adds "selection-colours":
# the one change that alters a rule's text, the "::selection" rule of Dark
# Reader's user-agent style (its two colours written as colours instead of
# var(--darkreader-...-<hex>, <the same colour>)), measured and shown to give
# the same pixels (docs/review/tests-and-performance.md, "1.1.23, the colours of
# selected text").
KEPT_FAMILIES = ("shadow-host-walk", "color-variables", "style-groups", "shadow-texts",
                 "dark-copy", "shadow-styles-once", "declarations-modifiable", "variables-none",
                 "style-moves", "selection-colours")
DROPPED_MARKS = (
    "ikeSVGRect", "ikeWithSVGRects", "ikePendingSVG",                               # svg-sizes
    "ikeSheets", "the list is changed here and set once",                         # adopted-once
    "ikeAnyImageSelector",                                                        # image-selectors
    "one loop, the same text as filter",                                          # inline-style-key
    "ikeRuleText", "ikeWriteAll", "ikeGroupText",                                   # one-text
    "ikeVarRuleTexts",                                                            # var-rule-same-text
    "ikeMatchedSheets", "ikeNewSheet",                                             # adopted-vars-first
)


def test_the_engine_has_only_the_measured_changes():
    """The shipped engine carries the changes of the ten measured families
    and nothing of the ones dropped: every "I.K.E.:" note in it is one of a
    kept change, each once."""
    import re

    from ike.config import RES_DIR
    tool = build_tool()
    families = {name for name, _old, _new in tool.PATCHES}
    assert {f for f in KEPT_FAMILIES if any(n == f or n.startswith(f + "-") for n in families)} == set(KEPT_FAMILIES)
    assert all(any(n == f or n.startswith(f + "-") for f in KEPT_FAMILIES) for n in families), families
    engine = (RES_DIR / "darkreader.js").read_bytes().decode()
    notes = re.findall(r"// I\.K\.E\.:[^\r\n]*", engine)
    dropped = shipped_dropped(tool)
    kept_notes = [m for n, _o, new in tool.PATCHES if n not in dropped
                  for m in re.findall(r"// I\.K\.E\.:[^\n]*", new)]
    assert notes and sorted(notes) == sorted(kept_notes) and len(set(notes)) == len(notes), notes
    for mark in DROPPED_MARKS:
        assert mark not in engine, mark
        assert all(mark not in new for _n, _o, new in tool.PATCHES), mark


# --- the builder's rules of 2026-11-24 (the owner's decisions; no network) ----------

# Dark Reader 4.9.135's own proxy injection (npm "darkreader", darkreader.js), the
# block PROXY_BLOCK takes out: with it, the shipped engine with I.K.E.'s patches
# undone is Dark Reader's engine again, so the builder can be run on the real
# engine here, offline.
UPSTREAM_PROXY_BLOCK = (
    "{\r\n"
    "            const proxyScript = createOrUpdateScript(\"darkreader--proxy\");\r\n"
    "            proxyScript.append(\r\n"
    "                `(${injectProxy})(${enableStyleSheetsProxy}, ${enableCustomElementRegistryProxy})`\r\n"
    "            );\r\n"
    "            document.head.insertBefore(\r\n"
    "                proxyScript,\r\n"
    "                document.head.querySelector(\".darkreader\")?.nextSibling ??\r\n"
    "                    document.head.firstElementChild\r\n"
    "            );\r\n"
    "            proxyScript.remove();\r\n"
    "        }")


def upstream_engine(tool):
    """Dark Reader's own engine, made again from the shipped one (None when the shipped engine had links
    removed or patches left out: then it cannot be made again exactly)."""
    from ike.config import RES_DIR
    notes = shipped_notes()
    if notes.get("links_removed") or notes.get("speed_patches_dropped"):
        return None
    engine = (RES_DIR / "darkreader.js").read_bytes().decode()
    for _name, old, new in tool.PATCHES:
        engine = engine.replace(new.replace("\n", "\r\n"), old.replace("\n", "\r\n"))
    return engine.replace(tool.PROXY_EVENT, UPSTREAM_PROXY_BLOCK)


@pytest.fixture
def upstream():
    tool = build_tool()
    lib = upstream_engine(tool)
    if lib is None:
        pytest.skip("the shipped engine was built with links removed or patches left out")
    return tool, lib


def node_ok(text):
    """node --check of a script (None without Node.js)."""
    return build_tool().node_parses(text)


def test_the_shipped_engine_is_rebuilt_byte_for_byte(upstream):
    """The real engine, made again from the shipped one, gives the shipped darkreader.js and
    darkreader-proxy.js byte for byte: nothing is left out or removed today. With
    IKE_DARKREADER_LIB (npm's darkreader.js of the version in use) the made-again engine is checked
    against it, and with IKE_DARKREADER_CONFIG (src/config of Dark Reader's repository at the lists'
    commit) darkreader-data.json too."""
    import os
    from pathlib import Path

    from ike.config import RES_DIR
    tool, lib = upstream
    engine, proxy_js, notes = tool.build_engine(lib)
    assert engine.encode() == (RES_DIR / "darkreader.js").read_bytes()
    assert proxy_js.encode() == (RES_DIR / "darkreader-proxy.js").read_bytes()
    assert notes == {"speed_patches_dropped": [], "links_removed": []}
    npm = os.environ.get("IKE_DARKREADER_LIB")
    if npm:
        assert Path(npm).read_bytes().decode() == lib
    cfg = os.environ.get("IKE_DARKREADER_CONFIG")
    if cfg and npm:
        data = json.loads((RES_DIR / "darkreader-data.json").read_text("utf-8"))
        _e, _p, rebuilt = tool.build(npm, cfg, data["lists_commit"], data["lists_date"])
        assert json.dumps(rebuilt, ensure_ascii=False, separators=(",", ":")) + "\n" == \
            (RES_DIR / "darkreader-data.json").read_text("utf-8")


def test_the_patch_families_are_what_the_code_needs():
    """PATCH_NEEDS: every speed patch is in one family, the families are the measured ones, and a
    family that uses a function or variable another family declares (ike...) needs that family."""
    import re
    tool = build_tool()
    assert set(tool.PATCH_NEEDS) == set(KEPT_FAMILIES)
    fams = {}
    for name, _old, new in tool.PATCHES:
        fams.setdefault(tool.patch_family(name), []).append(new)
    assert set(fams) == set(KEPT_FAMILIES)
    declared = {}
    for fam, texts in fams.items():
        for text in texts:
            for ident in re.findall(r"\b(?:function|const|let|var)\s+(ike[A-Z]\w*)", text):
                declared.setdefault(ident, fam)

    def needs(fam):
        out = set(tool.PATCH_NEEDS[fam])
        for x in tool.PATCH_NEEDS[fam]:
            out |= needs(x)
        return out
    for fam, texts in fams.items():
        for ident in set(re.findall(r"(?<![.\w])(ike[A-Z]\w*)", "".join(texts))):    # not a property
            owner = declared.get(ident)
            assert owner is None or owner == fam or owner in needs(fam), (fam, ident, owner)
    # the three dependencies are real ones
    assert declared["ikeShadowTexts"] == "shadow-texts" and declared["ikeColorOnRoot"] == "color-variables"
    assert declared["ikeGroup"] == "style-groups"


def test_a_speed_patch_that_no_longer_fits_is_left_out_and_the_rest_ships(upstream):
    """The real engine with the text of one speed patch changed: that family (and only what needs
    it) is left out, every other patch is made, the proxy change is there and the script still
    parses."""
    tool, lib = upstream
    anchor = old_text(tool.PATCHES, "style-moves-check").replace("\n", "\r\n")
    assert lib.count(anchor) == 1
    engine, _proxy, notes = tool.build_engine(lib.replace(anchor, anchor.replace("!==", "!= ")))
    assert [(d["family"], d["patches"]) for d in notes["speed_patches_dropped"]] == \
        [("style-moves", ["style-moves", "style-moves-check"])]
    for name, _old, new in tool.PATCHES:
        made = engine.count(new.replace("\n", "\r\n"))
        assert made == (0 if name.startswith("style-moves") else 1), name
    assert "ikeStyleSibling" not in engine and engine.count(tool.PROXY_EVENT) == 1
    assert node_ok(engine) in (True, None)
    # a family others need: selection-colours goes with color-variables
    anchor = old_text(tool.PATCHES, "color-variables-register").replace("\n", "\r\n")
    engine, _proxy, notes = tool.build_engine(lib.replace(anchor, anchor.replace("?.style", "?.style ")))
    assert [d["family"] for d in notes["speed_patches_dropped"]] == ["color-variables", "selection-colours"]
    assert "ikeColorOnRoot" not in engine and "ikePlainColor" not in engine
    assert engine.count(old_text(tool.PATCHES, "shadow-texts").replace("\n", "\r\n")) == 0     # made
    assert node_ok(engine) in (True, None)


def test_the_proxy_change_that_no_longer_fits_stops_the_build(upstream):
    """The proxy change is not a speed patch: without it the build stops."""
    tool, lib = upstream
    with pytest.raises(SystemExit, match="proxy injection"):
        tool.build_engine(lib.replace(UPSTREAM_PROXY_BLOCK, UPSTREAM_PROXY_BLOCK.replace(
            "proxyScript.remove();", "proxyScript.detach();")))
    with pytest.raises(SystemExit, match="injectProxy"):
        tool.build_engine(lib.replace("function injectProxy(", "function injectTheProxy("))


LINKY = """// see https://unknown.example/notes and https://www.patreon.com/darkreader
/* social: https://twitter.com/darkreaderapp */
/*! https://ko-fi.com/darkreader*/
const a = "https://www.patreon.com/darkreader";
const b = 'https://opencollective.com/darkreader';
const c = ["x", "https://twitter.com/darkreaderapp", "https://darkreader.org/blog/news-1"];
const d = `<a href="https://www.buymeacoffee.com/x">${a}</a>`;
const e = "https://fonts.googleapis.com/";
const f = url.startsWith("https://") || url.startsWith("moz-extension://");
const g = document.createElementNS("http://www.w3.org/2000/svg", "svg");
const h = "support us at patreon.com/darkreader";
const re = /https?:\\/\\/[^/]+/;
"""


def test_links_are_removed_by_kind_and_the_script_stays_the_same_code():
    tool = build_tool()
    out, removed = tool.scrub_links(LINKY, "darkreader.js")
    # comments lose the link, strings of a denied kind become "", a template loses only the link
    assert "// see  and \n/* social:  */\n/*! */\n" in out
    assert 'const a = "";' in out and "const b = '';" in out
    assert 'const c = ["x", "", ""];' in out
    assert 'const d = `<a href="">${a}</a>`;' in out
    assert 'const h = "";' in out
    # what Dark Reader needs stays: the allowed links, the schemes it compares with, a regular expression
    for kept in ('const e = "https://fonts.googleapis.com/";', 'url.startsWith("https://")',
                 'url.startsWith("moz-extension://")', '"http://www.w3.org/2000/svg"',
                 "const re = /https?:\\/\\/[^/]+/;"):
        assert kept in out, kept
    kinds = sorted((r["where"], r["kind"], r["host"]) for r in removed)
    assert kinds == [("comment", "donation", "ko-fi.com"), ("comment", "donation", "www.patreon.com"),
                     ("comment", "social", "twitter.com"),
                     ("comment", "unknown", "unknown.example"), ("string", "donation", "opencollective.com"),
                     ("string", "donation", "patreon.com"), ("string", "donation", "www.patreon.com"),
                     ("string", "news", "darkreader.org"), ("string", "social", "twitter.com"),
                     ("template", "donation", "www.buymeacoffee.com")], kinds
    assert tool.code_shape(out) == tool.code_shape(LINKY)
    assert node_ok(out) in (True, None) and node_ok(LINKY) in (True, None)
    # nothing left to remove; a second pass changes nothing
    assert tool.scrub_links(out, "darkreader.js") == (out, [])


@pytest.mark.parametrize("text,why", [
    ('const a = "https://cdn.unknown.example/x.js";', "an unknown link in a string"),
    ("const a = `see https://unknown.example/${x}`;", "an unknown link in a template literal"),
    ('if (location.href === "https://www.youtube.com/@darkreader") {}', "a social link the code compares with"),
    ('if (url.startsWith("https://www.patreon.com/")) {}', "a donation link the code compares with"),
    ('const map = {"https://twitter.com/x": 1};', "a social link the code compares with"),
])
def test_a_link_a_person_must_judge_stops_the_build(text, why):
    tool = build_tool()
    with pytest.raises(SystemExit, match="links: darkreader.js: line 1, .*%s" % why):
        tool.scrub_links(text, "darkreader.js")


def test_links_in_the_real_engine(upstream):
    """Links put into the real engine: removed, the rest of the build as usual; an unknown one stops it."""
    tool, lib = upstream
    extra = ("\r\n// news: https://darkreader.org/blog/whats-new\r\n"
             "var ikeTestDonate = \"https://www.patreon.com/darkreader\";\r\n")
    engine, _proxy, notes = tool.build_engine(lib + extra)
    assert engine.endswith("\r\n// news: \r\nvar ikeTestDonate = \"\";\r\n")
    assert [(r["kind"], r["host"]) for r in notes["links_removed"]] == [("news", "darkreader.org"),
                                                                       ("donation", "www.patreon.com")]
    assert node_ok(engine) in (True, None)
    with pytest.raises(SystemExit, match="links: darkreader.js: .*an unknown link"):
        tool.build_engine(lib + "\r\nvar ikeTest = \"https://cdn.unknown.example/a.js\";\r\n")


def test_a_new_network_call_stops_the_build(upstream):
    tool, lib = upstream
    with pytest.raises(SystemExit, match="network calls: darkreader.js: sendBeacon 0 -> 1"):
        tool.build_engine(lib + "\r\nnavigator.sendBeacon(\"/x\", y);\r\n")
    with pytest.raises(SystemExit, match="network calls: darkreader.js: fetch 4 -> 5"):
        tool.build_engine(lib + "\r\nfetch(y);\r\n")
    # in a comment or a string it is no call
    tool.build_engine(lib + "\r\n// fetch(y) and new WebSocket(z)\r\nvar ikeTest = \"fetch(y)\";\r\n")


def test_the_api_of_the_panel_must_stay(upstream):
    """DarkReader.enable(theme, fixes), disable, setFetchMethod and the theme's fields I.K.E.'s panel
    and darkmode.js use: gone or changed, the build stops."""
    import re
    tool, lib = upstream
    assert tool.api_problems(lib) == []
    cases = {"exports.setFetchMethod": lib.replace("exports.setFetchMethod = setFetchMethod;", ""),
             "exports.disable": lib.replace("exports.disable = disable;", "exports.off = disable;"),
             "theme.scrollbarColor (DEFAULT_THEME)": lib.replace("        scrollbarColor: \"\",\r\n", ""),
             "enable(theme, fixes): its second parameter": lib.replace(
                 "function enable(themeOptions = {}, fixes = null) {", "function enable(themeOptions = {}) {")}
    for what, text in cases.items():
        assert text != lib, what
        with pytest.raises(SystemExit, match="API that I.K.E.'s panel uses .*%s" % re.escape(what)):
            tool.build_engine(text)


def test_the_site_fixes_cannot_carry_a_script(tmp_path):
    """darkreader-data.json is data (CSS for a style element, selectors, flags): anything that looks
    like a script stops the build; the shipped lists have none."""
    from ike.config import RES_DIR
    tool = build_tool()
    data = json.loads((RES_DIR / "darkreader-data.json").read_text("utf-8"))
    assert tool.data_problems(data) == []
    for css in ("a { background: url(javascript:alert(1)) }", "</style><script>alert(1)</script>",
                "x { behavior: url(a.htc) }", "x { width: expression(alert(1)) }"):
        bad = dict(data, fixes=data["fixes"] + [{"url": ["bad.example"], "css": css}])
        assert tool.data_problems(bad), css
    assert tool.data_problems(dict(data, fixes=[{"url": ["x"], "script": "a"}]))
    lib = tmp_path / "lib.js"
    lib.write_bytes(fake_engine(tool.PATCHES).encode())
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "dynamic-theme-fixes.config").write_text("*\n\nCSS\nbody { color: red }\n\n====\n\nbad.example\n\n"
                                                    "CSS\na { background: url('javascript:alert(1)') }\n")
    (cfg / "dark-sites.config").write_text("dark.example\n")
    (cfg / "detector-hints.config").write_text("own.example\n\nNO DARK THEME\n")
    with pytest.raises(SystemExit, match="could be a script: fixes\\[1\\].css \\(bad.example\\)"):
        tool.build(lib, cfg)


def test_the_shipped_dark_reader_has_only_allowed_links():
    """The guard on what ships: in darkreader.js, darkreader-proxy.js and darkmode.js every absolute
    link is allowed (LINKS_ALLOWED, or a bare scheme the code compares with), none of a denied kind;
    the network calls and the panel's API are those the builder checks."""
    from ike.config import RES_DIR
    tool = build_tool()
    for name in ("darkreader.js", "darkreader-proxy.js", "darkmode.js"):
        text = (RES_DIR / name).read_text("utf-8")
        found = tool.scan_links(text)
        assert found, name
        for f in found:
            assert f["verdict"] == "keep", (name, f)
            assert f["url"] in tool.LINKS_ALLOWED or f["url"].endswith("://"), (name, f)
            assert not tool.link_kind(f["url"]), (name, f)
    assert tool.network_calls((RES_DIR / "darkreader.js").read_text("utf-8")) == tool.NETWORK_CALLS["darkreader.js"]
    assert tool.network_calls((RES_DIR / "darkreader-proxy.js").read_text("utf-8")) == {}
    assert tool.api_problems((RES_DIR / "darkreader.js").read_text("utf-8")) == []
    # darkmode.js calls only what PANEL_API keeps
    mode = (RES_DIR / "darkmode.js").read_text("utf-8")
    import re
    assert set(re.findall(r"\bDR\.(\w+)\(", mode)) <= set(tool.PANEL_API["exports"])


# --- in the browser -------------------------------------------------------------

PAGES = {
    # a strict policy: no inline script at all; the page's own script adds its styles
    # through the CSSOM (insertRule) and as a constructed style sheet
    "/csp": ("<!doctype html><html><head><title>csp</title><script src='/app.js'></script></head>"
             "<body><div id='a' class='box'>insertRule</div><div id='b' class='adopted'>adopted</div>"
             "<p style='height:400px'>text</p></body></html>",
             {"Content-Security-Policy": "script-src 'self'; style-src 'self' 'unsafe-inline'"}),
    "/app.js": ("document.addEventListener('DOMContentLoaded', function () {"
                "  var s = document.createElement('style'); document.head.appendChild(s);"
                "  s.sheet.insertRule('.box { background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); height: 60px }', 0);"
                "  var c = new CSSStyleSheet();"
                "  c.replaceSync('.adopted { background-color: rgb(250, 250, 250); color: rgb(10, 10, 10); height: 60px }');"
                "  document.adoptedStyleSheets = [c];"
                "  document.title = 'ready';"
                "});", {"Content-Type": "application/javascript"}),
    # a site with a dark theme of its own
    "/dark": ("<!doctype html><html><head><title>dark</title><style>html,body{background:#121212;color:#eee}"
              "main{height:600px}</style></head><body><main><h1>Own dark theme</h1><p>Some text here.</p>"
              "<p>More text.</p></main></body></html>", {}),
    # an ordinary light page
    "/light": ("<!doctype html><html><head><title>light</title><style>body{background:#fff;color:#111}"
               "main{height:600px}</style></head><body><main><h1>Light</h1><p>Text.</p></main></body></html>", {}),
}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body, headers = PAGES.get(self.path.split("?")[0], ("", {}))
            if not body:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", headers.get("Content-Type", "text/html; charset=utf-8"))
            for k, v in headers.items():
                if k != "Content-Type":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"
READ = """JSON.stringify({
  dr: document.querySelectorAll('style.darkreader, .darkreader--sync').length,
  html: getComputedStyle(document.documentElement).backgroundColor,
  a: document.getElementById('a') ? getComputedStyle(document.getElementById('a')).backgroundColor : null,
  b: document.getElementById('b') ? getComputedStyle(document.getElementById('b')).backgroundColor : null,
  body: getComputedStyle(document.body).backgroundColor,
  title: document.title})"""

def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 500
    for name in ("csp", "dark", "light"):
        yield from load(view, SITE + "/" + name)
        yield 2500
        out[name] = json.loads((yield from js(view, READ)))
        # the page itself cannot start Dark Reader's proxy: its event carries a token of the session
        out[name]["page_starts_proxy"] = (yield from js(view,
            "document.dispatchEvent(new CustomEvent('__darkreader__stylesheetProxy__arg', {detail: {}})); "
            "document.documentElement.dataset.darkreaderProxyInjected === 'true'"))
'''


def lightness(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    if not m:
        return None
    r, g, b = (int(x) for x in m.groups())
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def test_dark_mode_on_for_every_site(run_ike, site):
    steps = STEPS.replace("__SITE__", site)
    out = run_ike(steps, settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    # the first site opened from the new tab page is dark too (a script of the page alone
    # missed it when the engine started the site in another process)
    csp = out["csp"]
    assert csp["title"] == "ready" and csp["dr"] > 0, csp
    # the styles the page made itself, under a policy that blocks inline scripts, are darkened too
    assert lightness(csp["a"]) < 0.3, csp
    assert lightness(csp["b"]) < 0.3, csp
    # a site with its own dark theme is recognised and left as it is
    dark = out["dark"]
    assert dark["dr"] == 0 and dark["body"] == "rgb(18, 18, 18)", dark
    assert dark["page_starts_proxy"] is False
    # an ordinary light page is made dark
    assert out["light"]["dr"] > 0 and lightness(out["light"]["body"]) < 0.3, out["light"]


def test_a_site_turned_dark_by_hand_is_always_dark(run_ike, site):
    """Dark mode off, the site on its own list: no detector, no list can undo the user's choice."""
    steps = STEPS.replace("__SITE__", site)
    out = run_ike(steps, settings={"dark_mode": "off", "dark_engine": "reader", "dark_sites": ["127.0.0.1"]},
                  timeout=150)
    assert out["dark"]["dr"] > 0
    assert out["csp"]["dr"] > 0 and lightness(out["csp"]["a"]) < 0.3


def test_dark_mode_off_changes_nothing(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "off", "dark_engine": "reader"},
                  timeout=150)
    assert out["light"]["dr"] == 0 and out["light"]["body"] == "rgb(255, 255, 255)"
    assert out["csp"]["dr"] == 0 and out["csp"]["a"] == "rgb(255, 255, 255)"
    assert json.dumps(out["dark"]["body"]) == '"rgb(18, 18, 18)"'


SELECTION_STEPS = JS + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/light")
    yield 2500
    out["sel"] = json.loads((yield from js(view, """JSON.stringify({
      css: (document.querySelector('style.darkreader--user-agent') || {}).textContent || '',
      bg: getComputedStyle(document.body, '::selection').backgroundColor,
      fg: getComputedStyle(document.body, '::selection').color})""")))
'''


def test_the_colours_of_selected_text_are_written_as_colours(run_ike, site):
    """selection-colours (1.1.23): Dark Reader's "::selection" rule gives its two
    colours as colours, not as var(--darkreader-...-<hex>, <the same colour>),
    and selected text has the same colours as before (rgb(0, 77, 170) behind
    rgb(232, 230, 227), Dark Reader's own for the default theme)."""
    out = run_ike(SELECTION_STEPS.replace("__SITE__", site),
                  settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    sel = out["sel"]
    start = sel["css"].find("::selection {")
    sel["rule"] = sel["css"][start:sel["css"].find("}", start) + 1] if start >= 0 else ""
    del sel["css"]
    assert "background-color: #004daa !important;" in sel["rule"], sel
    assert "color: #e8e6e3 !important;" in sel["rule"] and "var(" not in sel["rule"], sel
    assert sel["bg"] == "rgb(0, 77, 170)" and sel["fg"] == "rgb(232, 230, 227)", sel


# --- what Dark Reader darkens (I.K.E.'s changes to its engine keep all of it) ------

CASES = r"""<!doctype html><html><head><title>cases</title>
<style>
body { background: #fff; color: #111 }
.box { background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); height: 30px }
#fixvar { background-color: #fff; height: 20px }
.mv { background-color: rgb(255, 255, 254); height: 20px }
.img1 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
.img2 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
.img3 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
</style>
<style id="moved">.mv { background-color: rgb(254, 254, 254) }</style>
</head><body>
<div id="plain" class="box">plain</div>
<div id="inline" style="background-color: rgb(250, 250, 250); color: rgb(10, 10, 10); height: 30px">inline</div>
<div id="fixvar">fix</div>
<div id="mv" class="mv">moved style</div>
<svg id="icon" width="16" height="16"><path id="iconpath" d="M0 0h16v16H0z" fill="#000000"/></svg>
<svg id="chart" width="300" height="200"><rect id="bigrect" width="300" height="200" fill="#ffffff"/>
<rect id="smallrect" x="1" y="1" width="10" height="10" fill="#ffffff"/>
<line id="line" x1="0" y1="0" x2="300" y2="200" stroke="#000000"/></svg>
<div id="dsd"><template shadowrootmode="open"><style>.d { background-color: #fff; height: 20px }</style>
<div class="d" id="dsdin">declarative shadow root</div></template></div>
<div id="host"></div>
<iframe id="frame" src="/frame" width="300" height="100"></iframe>
<script src="/cases.js"></script>
</body></html>"""

CASES_JS = r"""
window.addEventListener('load', function () {
  // a shadow root with its own style element, an inline style and an adopted style sheet
  var root = document.getElementById('host').attachShadow({mode: 'open'});
  root.innerHTML = '<style>.s { background-color: #fff; color: #000; height: 30px }</style>' +
    '<div class="s" id="sdiv">shadow</div><div id="sinline" style="background-color: #ffffff; height: 30px">x</div>' +
    '<div class="a" id="sadopted">adopted</div>';
  var sheet = new CSSStyleSheet();
  sheet.replaceSync('.a { background-color: rgb(253, 253, 253); color: rgb(0, 0, 0); height: 30px }');
  root.adoptedStyleSheets = [sheet];
  // a colour the page shows only now, from a style element added now
  var st = document.createElement('style');
  st.textContent = '.newc { background-color: rgb(255, 250, 240); color: rgb(5, 5, 5); height: 30px }';
  document.head.appendChild(st);
  var d = document.createElement('div'); d.className = 'newc'; d.id = 'newc'; d.textContent = 'new colour';
  document.body.appendChild(d);
  // a chart drawn after the page loaded: big shapes are backgrounds, small ones are like text
  var ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '300'); svg.setAttribute('height', '200');
  [['dynbig', 0, 0, 300, 150], ['dynsmall', 2, 2, 8, 8], ['dynsmall2', 20, 2, 8, 8]].forEach(function (r) {
    var e = document.createElementNS(ns, 'rect');
    e.id = r[0]; e.setAttribute('x', r[1]); e.setAttribute('y', r[2]);
    e.setAttribute('width', r[3]); e.setAttribute('height', r[4]); e.setAttribute('fill', '#fafafa');
    svg.appendChild(e);
  });
  document.body.appendChild(svg);
  setTimeout(function () {
    // fill colours changed later; a large change of the page; a style element moved
    // to the end of the head (its rules now come later, Dark Reader's copy must follow)
    document.getElementById('dynbig').setAttribute('fill', '#f0f0f0');
    document.getElementById('dynsmall').setAttribute('fill', '#f0f0f0');
    var many = document.createElement('div');
    for (var i = 0; i < 1200; i++) many.appendChild(document.createElement('span'));
    document.body.appendChild(many);
    for (var j = 0; j < 1100; j++) document.body.appendChild(document.createElement('i'));
    document.head.appendChild(document.getElementById('moved'));
    // elements for background-image rules that matched nothing until now
    var img = document.createElement('div'); img.className = 'img2'; img.id = 'img2';
    document.body.appendChild(img);
    document.title = 'ready';
  }, 600);
});
"""

FRAME = ("<!doctype html><html><head><style>body { background: #fff; color: #000 }</style></head>"
         "<body><p id='fp'>frame</p></body></html>")

CASE_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  function cs(el) { return el ? getComputedStyle(el) : null; }
  var root = document.getElementById('host').shadowRoot, dsd = document.getElementById('dsd').shadowRoot;
  var fdoc = document.getElementById('frame').contentDocument;
  var moved = document.getElementById('moved');
  var rootStyle = getComputedStyle(document.documentElement);
  return JSON.stringify({
    title: document.title,
    body: cs(document.body).backgroundColor,
    plain: [cs(document.getElementById('plain')).backgroundColor, cs(document.getElementById('plain')).color],
    inline: [cs(document.getElementById('inline')).backgroundColor, cs(document.getElementById('inline')).color],
    fixvar: cs(document.getElementById('fixvar')).backgroundColor,
    rootvar: rootStyle.getPropertyValue('--darkreader-background-ffffff').trim(),
    newcvar: rootStyle.getPropertyValue('--darkreader-background-fffaf0').trim(),
    newc: [cs(document.getElementById('newc')).backgroundColor, cs(document.getElementById('newc')).color],
    mv: cs(document.getElementById('mv')).backgroundColor,
    img2: cs(document.getElementById('img2')).backgroundImage.slice(0, 40),
    movedcopy: !!(moved.nextElementSibling && moved.nextElementSibling.classList.contains('darkreader--sync')),
    icon: cs(document.getElementById('iconpath')).fill,
    bigrect: cs(document.getElementById('bigrect')).fill,
    smallrect: cs(document.getElementById('smallrect')).fill,
    line: cs(document.getElementById('line')).stroke,
    dynbig: cs(document.getElementById('dynbig')).fill,
    dynsmall: cs(document.getElementById('dynsmall')).fill,
    dynsmall2: cs(document.getElementById('dynsmall2')).fill,
    sdiv: [cs(root.getElementById('sdiv')).backgroundColor, cs(root.getElementById('sdiv')).color],
    sinline: cs(root.getElementById('sinline')).backgroundColor,
    sadopted: [cs(root.getElementById('sadopted')).backgroundColor, cs(root.getElementById('sadopted')).color],
    dsdin: dsd ? cs(dsd.getElementById('dsdin')).backgroundColor : null,
    frame: fdoc ? [getComputedStyle(fdoc.body).backgroundColor, getComputedStyle(fdoc.getElementById('fp')).color]
                : null
  });
})()"""

def steps(ike, qapp, out):
    from ike import darkfixes
    common = darkfixes.fix_for
    def fix_for(url):
        # a site's fix that names a colour variable without a fallback, as some in the list do
        fix = dict(common(url))
        fix["css"] = ((fix.get("css") or "")
                      + "\n#fixvar { background-color: var(--darkreader-background-ffffff) !important; }")
        return fix
    darkfixes.fix_for = fix_for
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/cases")
    for _ in range(40):
        yield 250
        if (yield from js(view, "document.title")) == "ready":
            break
    yield 2500
    out.update(json.loads((yield from js(view, READ))))
'''


def test_what_dark_reader_darkens(run_ike, site):
    """Every kind of content Dark Reader darkens is still darkened with I.K.E.'s
    changes to its engine: style sheets, inline styles, SVG shapes (big ones as
    backgrounds, small ones as text, as Dark Reader tells them apart), content
    added after the page loaded, a style element the page moves, shadow roots
    (made by script or declared in the page) with their style elements, inline
    styles and adopted style sheets, a frame of the same site, and a site's fix
    that names a colour variable."""
    PAGES["/cases"] = (CASES, {})
    PAGES["/cases.js"] = (CASES_JS, {"Content-Type": "application/javascript"})
    PAGES["/frame"] = (FRAME, {})
    out = run_ike(CASE_STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=150)
    assert out.get("title") == "ready", out

    def dark(c):
        return lightness(c) is not None and lightness(c) < 0.3

    def light(c):
        return lightness(c) is not None and lightness(c) > 0.6
    assert dark(out["body"]), out
    for key in ("plain", "inline", "newc", "sdiv", "sadopted", "frame"):
        bg, fg = out[key]
        assert dark(bg) and light(fg), (key, out[key])
    for key in ("mv", "sinline", "dsdin", "bigrect", "dynbig"):
        assert dark(out[key]), (key, out[key])
    # a light background image whose rule matched nothing until the element came is replaced
    assert out["img2"].startswith('url("data:image/svg+xml;base64,'), out["img2"]
    # small shapes take the colour of text: white stays light, black becomes light
    for key in ("icon", "smallrect", "dynsmall", "dynsmall2"):
        assert light(out[key]), (key, out[key])
    assert out["line"] != "rgb(0, 0, 0)" and lightness(out["line"]) > 0.3, out["line"]
    # the moved style element's copy followed it
    assert out["movedcopy"], out
    # the fix's variable is defined; a colour no fix names needs no variable on :root
    assert dark(out["fixvar"]) and out["rootvar"], out
    assert out["newcvar"] == "", out


# --- identical style elements share one Dark Reader copy (the cascade is unchanged) --

ICON = "<svg class='icon' width='16' height='16'><style>.ic { fill: #464646 }</style><path class='ic' d='M0 0h16v16H0z'/></svg>"
GROUPS = ("<!doctype html><html><head><title>groups</title>"
          "<style>.m { height: 10px }</style></head><body>"
          "<div id='icons'>" + ICON * 5 + "<svg id='x1'><style>.ic { fill: #eeeeee }</style></svg>"
          + ICON.replace("class='icon'", "class='icon' id='i6'") + "</div>"
          "<svg><style>.ref1 { fill: #464646 }</style><path id='ref1' class='ref1' d='M0 0h1v1H0z'/></svg>"
          "<svg><style>.ref2 { fill: #eeeeee }</style><path id='ref2' class='ref2' d='M0 0h1v1H0z'/></svg>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style>.m { background-color: #ff0000 }</style>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style media='(min-width: 1px)'>.mref { background-color: #fafafa }</style>"
          "<style>.mref2 { background-color: #ff0000 }</style>"
          "<div id='m' class='m'>m</div><div id='mref' class='mref' style='height: 10px'>ref</div>"
          "<div id='mref2' class='mref2' style='height: 10px'>ref</div>"
          "<div id='host'></div><script src='/groups.js'></script></body></html>")

GROUPS_JS = r"""
var SICON = "<svg class='sicon' width='16' height='16'><style>.sc { fill: #464646 }</style><path class='sc' d='M0 0h16v16H0z'/></svg>";
var shadow = document.getElementById('host').attachShadow({mode: 'open'});
shadow.innerHTML = SICON + SICON + "<svg><style>.sc { fill: #eeeeee }</style></svg>" + SICON;
function groupStyles() {
  return Array.prototype.filter.call(document.querySelectorAll('svg.icon > style'), function (s) {
    return s.textContent === '.ic { fill: #464646 }';
  });
}
window.phase = function (n) {
  var icons = document.getElementById('icons'), x1 = document.getElementById('x1');
  if (n === 1) {       // the last identical one moved before a different rule that it overrode
    icons.insertBefore(document.getElementById('i6'), x1);
    shadow.appendChild(document.createRange().createContextualFragment("<svg><style>.sc { fill: #eeeeee }</style></svg>"));
  } else if (n === 2) {   // a new identical one after it
    var t = document.createElement('template'); t.innerHTML = "<svg class='icon' id='i7' width='16' height='16'><style>.ic { fill: #464646 }</style><path class='ic' d='M0 0h16v16H0z'/></svg>";
    icons.appendChild(t.content);
    var u = document.createElement('template'); u.innerHTML = SICON; shadow.appendChild(u.content);
  } else if (n === 3) {   // that one removed again
    document.getElementById('i7').remove();
  } else if (n === 4) {   // texts changed: the different rule's, and the last of a group's
    x1.querySelector('style').textContent = '.ic { fill: #464646 }';
    document.querySelectorAll('style[media="(min-width: 1px)"]')[2].textContent = '.m { background-color: #ff0000 }';
  } else if (n === 5) {   // a rule added through the CSSOM to the last identical one
    x1.remove();
    var g = groupStyles(); g[g.length - 1].sheet.insertRule('.ic { fill: #eeeeee }', 1);
    var ms = document.querySelectorAll('style[media="(min-width: 1px)"]'); ms[2].sheet.insertRule('.m { background-color: #ff0000 }', 1);
  } else if (n === 6) {   // a large change of the page that also puts the first icon last
    var many = document.createElement('div');
    for (var i = 0; i < 1500; i++) many.appendChild(document.createElement('span'));
    document.body.appendChild(many);
    icons.appendChild(icons.querySelector('svg.icon'));
  }
  document.title = 'phase' + n;
};
document.title = 'phase0';
"""

GROUP_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  function fill(el) { return getComputedStyle(el).fill; }
  var shadow = document.getElementById('host').shadowRoot;
  var copies = Array.prototype.filter.call(document.querySelectorAll('svg.icon > style'), function (s) {
    return s.nextElementSibling && s.nextElementSibling.classList.contains('darkreader--sync');
  }).length;
  return JSON.stringify({
    title: document.title,
    ic: Array.prototype.map.call(document.querySelectorAll('path.ic'), fill),
    sc: Array.prototype.map.call(shadow.querySelectorAll('path.sc'), fill),
    ref1: fill(document.getElementById('ref1')), ref2: fill(document.getElementById('ref2')),
    m: getComputedStyle(document.getElementById('m')).backgroundColor,
    mref: getComputedStyle(document.getElementById('mref')).backgroundColor,
    mref2: getComputedStyle(document.getElementById('mref2')).backgroundColor,
    icons: document.querySelectorAll('svg.icon').length, copies: copies
  });
})()"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/groups")
    yield 2000
    out["phases"] = [json.loads((yield from js(view, READ)))]
    for n in range(1, 7):
        yield from js(view, "phase(%d)" % n)
        yield 1200
        out["phases"].append(json.loads((yield from js(view, READ))))
'''


def test_identical_style_elements_share_one_copy(run_ike, site):
    """Many identical style elements (an SVG icon repeated, as on the
    Complex-DOM pages of Speedometer) share one Dark Reader copy, after the
    last of them; the colours are those of the rule that wins in the page's
    own cascade, also when the page moves, adds or removes them, puts a
    different rule between them, changes their text or their rules, inside a
    shadow root and with a media attribute."""
    PAGES["/groups"] = (GROUPS, {})
    PAGES["/groups.js"] = (GROUPS_JS, {"Content-Type": "application/javascript"})
    out = run_ike(GROUP_STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=150)
    phases = out.get("phases")
    assert phases and len(phases) == 7, out
    # which rule wins in the page's own cascade, phase by phase (#464646 -> ref1, #eeeeee -> ref2);
    # in phase 5 Dark Reader itself does not follow a rule added through the CSSOM to an SVG
    # style element, so its copy (#464646) still wins, as without I.K.E.'s change
    expect_ic = ["ref1", "ref2", "ref1", "ref2", "ref1", "ref1", "ref1"]
    expect_m = ["mref"] * 4 + ["mref2"] * 3
    expect_sc = ["ref1", "ref2", "ref1", "ref1", "ref1", "ref1", "ref1"]
    for n, p in enumerate(phases):
        assert p["title"] == "phase%d" % n, p
        assert p["ref1"] != p["ref2"] and p["ref1"] != "rgb(70, 70, 70)", p
        assert set(p["ic"]) == {p[expect_ic[n]]}, (n, p)
        assert set(p["sc"]) == {p[expect_sc[n]]}, (n, p)
        assert p["m"] == p[expect_m[n]] and lightness(p["m"]) < 0.3, (n, p)
    # one copy for the five-to-seven identical icons, not one each
    assert phases[0]["icons"] == 6 and phases[0]["copies"] == 1, phases[0]


# --- groups and disabled style elements (1.1.18 review) --------------------------
# The same page twice: once with identical style elements (they share one copy)
# and once with each text made unique by a comment (no group: Dark Reader's own
# behaviour, one copy each). Every phase must give the same colours in both.
def disabled_page(unique):
    def st(i, text, sid=""):
        body = text + ("/*%d*/" % i if unique else "")
        return "<style%s>%s</style>" % (" id='%s'" % sid if sid else "", body)
    light, red = ".d { background-color: #fafafa }", ".d { background-color: #ff0000 }"
    return ("<!doctype html><html><head><title>disabled</title></head><body>"
            + st(1, light, "s1") + st(2, red, "r") + st(3, light, "s3") + st(4, light, "s4")
            + "<div id='d' class='d' style='height: 10px'>d</div>"
            "<script src='/disabled.js'></script></body></html>")


DISABLED_JS = r"""
var UNIQUE = /\/\*\d+\*\//.test(document.getElementById('s1').textContent);
var n = 10;
function light() { n++; var s = document.createElement('style');
  s.textContent = '.d { background-color: #fafafa }' + (UNIQUE ? '/*' + n + '*/' : ''); return s; }
document.getElementById('s4').disabled = true;          // the last one starts disabled
window.phase = function (k) {
  var s1 = document.getElementById('s1'), s3 = document.getElementById('s3'), s4 = document.getElementById('s4');
  if (k === 1) { s3.disabled = true; }                  // every identical one after the red rule disabled
  else if (k === 2) { s3.sheet.disabled = false; s4.sheet.disabled = false; s1.sheet.disabled = true; } // CSSOM
  else if (k === 3) { document.body.insertBefore(s1, document.getElementById('d')); }  // a disabled one moved last
  else if (k === 4) { s4.remove(); s3.remove(); }                             // enabled ones removed
  else if (k === 5) { var s = light(); s.disabled = true; document.body.insertBefore(s, document.getElementById('d'));
                      s1.disabled = false; }                                    // a disabled one added
  else if (k === 6) { var a = light(); document.head.appendChild(a); a.disabled = true;   // added, disabled at once
                      document.body.insertBefore(document.getElementById('r'), document.getElementById('d')); }
  document.title = 'phase' + k;
};
document.title = 'phase0';
"""

DISABLED_STEPS = JS + r'''
SITE = "__SITE__"
READ = """JSON.stringify({title: document.title, d: getComputedStyle(document.getElementById('d')).backgroundColor,
  styles: Array.prototype.map.call(document.querySelectorAll('style:not(.darkreader)'), function (s) {
    return (s.id || '-') + (s.sheet && s.sheet.disabled ? ':off' : ':on'); }).join(' ')})"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for page in ("same", "unique"):
        yield from load(view, SITE + "/disabled-" + page)
        yield 2000
        rows = [json.loads((yield from js(view, READ)))]
        for k in range(1, 7):
            yield from js(view, "phase(%d)" % k)
            yield 1200
            rows.append(json.loads((yield from js(view, READ))))
        out[page] = rows
'''


def test_groups_with_disabled_style_elements_change_no_colour(run_ike, site):
    """Identical style elements with different enabled states (the disabled
    property, also through the CSSOM), moved, removed, added disabled: the
    colours with the shared copy are exactly those of Dark Reader's own one
    copy per element, in every phase."""
    PAGES["/disabled-same"] = (disabled_page(False), {})
    PAGES["/disabled-unique"] = (disabled_page(True), {})
    PAGES["/disabled.js"] = (DISABLED_JS, {"Content-Type": "application/javascript"})
    out = run_ike(DISABLED_STEPS.replace("__SITE__", site),
                  settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    same, unique = out.get("same"), out.get("unique")
    assert same and unique and len(same) == len(unique) == 7, out
    for k, (a, b) in enumerate(zip(same, unique)):
        assert a["title"] == b["title"] == "phase%d" % k, (a, b)
        assert a["styles"] == b["styles"], (k, a, b)            # the same states in both pages
        assert a["d"] == b["d"], ("a colour changed by the shared copy", k, a, b)


# --- groups and style elements filled through the CSSOM (CSS-in-JS) ----------------
# emotion / MUI and styled-components make empty <style> elements and fill them
# with sheet.insertRule: the texts are the same (empty, or a common base) and
# the rules differ. Such elements must never share a copy. The same page twice,
# as above: "same" as those libraries write it, "unique" with a comment in each
# text, which never groups (Dark Reader's own one copy per element).
def cssinjs_page(unique):
    boxes = "".join("<div id='%s' class='%s' style='height: 10px'>%s</div>" % (c, c, c) for c in "abcdefghijklmnop")
    return ("<!doctype html><html><head><title>cssinjs</title><script>var UNIQUE = %s;</script>"
            "<script src='/cssinjs.js'></script></head><body>" % ("true" if unique else "false")
            + boxes + "<script>document.title = 'phase0';</script></body></html>")


CSSINJS_JS = r"""
var n = 0;
function filled(cls, text) {              // a style element made by script, its rule added through the CSSOM
  var s = document.createElement('style');
  s.textContent = (text || '') + (UNIQUE ? '/*' + (++n) + '*/' : '');
  document.head.appendChild(s);
  if (cls) s.sheet.insertRule('.' + cls + ' { background-color: #fff; color: #000 }', s.sheet.cssRules.length);
  return s;
}
// while the page loads: empty texts, then a common text, each with a rule of its own
filled('a'); filled('b'); filled('c');
filled('d', '.base { margin: 0 }'); filled('e', '.base { margin: 0 }'); filled('f', '.base { margin: 0 }');
var later = [];
window.phase = function (k) {
  if (k === 1) {            // the same after the page loaded
    filled('g'); filled('h'); filled('i');
    filled('j', '.base { margin: 0 }'); filled('k', '.base { margin: 0 }'); filled('l', '.base { margin: 0 }');
    later = [filled(''), filled(''), filled('m'), filled('m')];      // two empty ones, two really identical ones
  } else if (k === 2) {     // rules added later to elements that were empty or identical until now
    later[0].sheet.insertRule('.n { background-color: #fff; color: #000 }', 0);
    later[1].sheet.insertRule('.o { background-color: #fff; color: #000 }', 0);
    later[2].sheet.insertRule('.p { background-color: #fff; color: #000 }', 1);
  } else if (k === 3) {     // a rule replaced by another one: the number of rules stays the same
    later[3].sheet.deleteRule(0);
    later[3].sheet.insertRule('.m { background-color: #000; color: #fff }', 0);
  }
  document.title = 'phase' + k;
};
"""

CSSINJS_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  var boxes = {};
  Array.prototype.forEach.call(document.querySelectorAll('body > div'), function (d) {
    var cs = getComputedStyle(d); boxes[d.id] = [cs.backgroundColor, cs.color]; });
  return JSON.stringify({title: document.title, boxes: boxes,
    styles: document.querySelectorAll('head > style:not(.darkreader)').length,
    copies: document.querySelectorAll('head > style.darkreader--sync').length});
})()"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for page in ("same", "unique"):
        yield from load(view, SITE + "/cssinjs-" + page)
        yield 2000
        rows = [json.loads((yield from js(view, READ)))]
        for k in range(1, 4):
            yield from js(view, "phase(%d)" % k)
            yield 1200
            rows.append(json.loads((yield from js(view, READ))))
        out[page] = rows
'''


def test_style_elements_filled_through_the_cssom_keep_their_own_copies(run_ike, site):
    """Style elements with the same text and different rules (CSS-in-JS: an
    empty element filled with insertRule) each keep their own Dark Reader copy:
    every box is dark, while the page loads and after it, also when the rules
    come later or are replaced, and the colours are those of Dark Reader's own
    one copy per element."""
    PAGES["/cssinjs-same"] = (cssinjs_page(False), {})
    PAGES["/cssinjs-unique"] = (cssinjs_page(True), {})
    PAGES["/cssinjs.js"] = (CSSINJS_JS, {"Content-Type": "application/javascript"})
    out = run_ike(CSSINJS_STEPS.replace("__SITE__", site),
                  settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    same, unique = out.get("same"), out.get("unique")
    assert same and unique and len(same) == len(unique) == 4, out
    ruled = ["abcdef", "abcdefghijklm", "abcdefghijklmnop", "abcdefghijklmnop"]     # boxes with a rule
    for k, (a, b) in enumerate(zip(same, unique)):
        assert a["title"] == b["title"] == "phase%d" % k, (a, b)
        assert a["styles"] == b["styles"] == (6 if k == 0 else 16), (k, a, b)
        assert a["boxes"] == b["boxes"], ("a colour changed by the shared copy", k, a, b)
        for box in ruled[k]:
            bg, fg = a["boxes"][box]
            assert lightness(bg) < 0.3 and lightness(fg) > 0.6, (k, box, a["boxes"])
    # the reference: one copy for each element
    assert [b["copies"] for b in unique] == [6, 16, 16, 16], unique
    # only the really identical ones share a copy (the two empty elements and the two ".m"
    # ones), until the page changes the rules of one of them
    assert [a["copies"] for a in same] == [6, 14, 16, 16], same
