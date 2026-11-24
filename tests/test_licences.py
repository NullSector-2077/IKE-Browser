"""Licences of what I.K.E. ships (1.1.18).

- LICENSE is the complete GNU GPL v3, as the FSF publishes it;
- the PKGBUILD installs every licence file, and the installed package has them
  (with IKE_TEST_APP, the tests of the installed package in GitHub Actions);
- the signed self-update carries them too;
- docs/THIRD-PARTY.md classifies every package the PKGBUILD depends on;
- the inventory of the Rust libraries (docs/THIRD-PARTY.md and
  licenses/RUST-CRATES.txt) agrees with itself and only names approved
  licences; tools/third-party.py refuses a licence that is not approved or
  cannot be read, never letting it pass in silence;
- the notice of the uBlock Origin scriptlets follows their file.

The check against the crates' own sources is tools/third-party.py --check and
cargo-deny, step "Licences" of tests.yml.
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
# sha256 of https://www.gnu.org/licenses/gpl-3.0.txt (35149 bytes; the same
# bytes as Debian's /usr/share/common-licenses/GPL-3)
GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
LICENCE_DIR = "usr/share/licenses/ike-browser"
# files the package must install there, besides those of licenses/
REQUIRED = ("LICENSE", "COPYRIGHT", "THIRD-PARTY.md", "RUST-STD-COPYRIGHT.html")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def doc():
    return (ROOT / "docs" / "THIRD-PARTY.md").read_text("utf-8")


# --- I.K.E.'s own licence ----------------------------------------------------

def test_licence_is_the_complete_gpl3():
    data = (ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(data).hexdigest() == GPL3_SHA256
    text = data.decode("ascii")
    assert text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007")
    assert "END OF TERMS AND CONDITIONS" in text and "How to Apply These Terms to Your New Programs" in text
    notice = (ROOT / "COPYRIGHT").read_text("utf-8")
    assert "Copyright (C) 2026 the I.K.E. project" in notice
    assert "either version 3 of the License, or (at your option) any later" in notice
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    assert "license=('GPL-3.0-or-later')" in pkgbuild


# --- what the package installs -----------------------------------------------

def test_pkgbuild_installs_every_licence():
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    line = re.search(r'^\s*install -Dm644 -t "\$pkgdir/usr/share/licenses/\$pkgname" (.+)$', pkgbuild, re.M)
    assert line, "the PKGBUILD installs no licences"
    sources = line.group(1).split()
    assert {"LICENSE", "COPYRIGHT", "licenses/*", "docs/THIRD-PARTY.md"} <= set(sources)
    assert 'COPYRIGHT-library.html" \\\n          "$pkgdir/usr/share/licenses/$pkgname/RUST-STD-COPYRIGHT.html"' \
        in pkgbuild
    # a Rust without that file (Arch's own rust package): the repository's copy
    assert 'install -Dm644 tools/licence-texts/RUST-STD-COPYRIGHT.html' in pkgbuild
    assert "Copyright notices for The Rust Standard Library" in \
        (ROOT / "tools" / "licence-texts" / "RUST-STD-COPYRIGHT.html").read_text("utf-8")
    # one plain folder: "install -t" takes files only
    assert all(p.is_file() for p in (ROOT / "licenses").iterdir())


def test_every_licence_file_is_documented():
    names = sorted(p.name for p in (ROOT / "licenses").iterdir())
    assert {"LICENSE.adblock-rust", "LICENSE.darkreader", "LICENSE.lucide", "LICENSE.orbitron",
            "LICENSE.phosphor", "RUST-CRATES.txt", "NOTICE.ubo-scriptlets", "LICENSE.breeze-icons"} <= set(names)
    notice, text = (ROOT / "COPYRIGHT").read_text("utf-8"), doc()
    for name in names + ["RUST-STD-COPYRIGHT.html"]:
        assert name in notice, name
        assert "`%s`" % name in text or "`licenses/%s`" % name in text, name


@pytest.mark.skipif(APP == ROOT, reason="only for the installed package (IKE_TEST_APP)")
def test_installed_package_has_the_licences():
    """The tests of the installed package (GitHub Actions): /usr/share/licenses."""
    installed = APP.parents[1] / "share" / "licenses" / "ike-browser"
    assert installed.is_dir(), installed
    have = {p.name for p in installed.iterdir()}
    want = set(REQUIRED) | {p.name for p in (ROOT / "licenses").iterdir()}
    assert want <= have, sorted(want - have)
    for p in (ROOT / "licenses").iterdir():
        assert (installed / p.name).read_bytes() == p.read_bytes(), p.name
    assert hashlib.sha256((installed / "LICENSE").read_bytes()).hexdigest() == GPL3_SHA256
    assert "Copyright notices for The Rust Standard Library" in \
        (installed / "RUST-STD-COPYRIGHT.html").read_text("utf-8")


def test_self_update_carries_the_licences(tmp_path):
    tool = load("make-release")
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(tool.build_payload())) as tar:
        names = set(tar.getnames())
        lic = tar.extractfile("ike/_licenses/LICENSE").read()
    assert "ike/_licenses" in names
    want = {"ike/_licenses/" + n for n in ("LICENSE", "COPYRIGHT", "THIRD-PARTY.md")}
    want |= {"ike/_licenses/" + p.name for p in (ROOT / "licenses").iterdir()}
    assert want <= names, sorted(want - names)
    assert hashlib.sha256(lic).hexdigest() == GPL3_SHA256
    # with the engine of a package just built: the licences that package installs
    usr = tmp_path / "pkg" / "ike-browser" / "usr"
    engine = usr / "lib" / "ike-browser" / "vendor" / "adblock"
    engine.mkdir(parents=True)
    installed = usr / "share" / "licenses" / "ike-browser"
    installed.mkdir(parents=True)
    for name in ("LICENSE", "RUST-STD-COPYRIGHT.html"):
        (installed / name).write_text(name)
    assert [n for _p, n in tool.licence_files(engine)] == ["LICENSE", "RUST-STD-COPYRIGHT.html"]
    assert [n for _p, n in tool.licence_files(tmp_path / "elsewhere")][:2] == ["COPYRIGHT", "LICENSE"]


# --- dependencies of the package ------------------------------------------------

def _pkgbuild_array(text, name):
    m = re.search(r"^%s=\((.*?)\)" % name, text, re.S | re.M)
    return [re.split(r"[:<>=]", x)[0] for x in re.findall(r"'([^']+)'", m.group(1))] if m else []


def test_every_dependency_of_the_package_is_classified():
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    text = doc()
    system = text.split("## From the system (category 4)", 1)[1].split("\n## ", 1)[0]
    build = text.split("## Build only (category 3)", 1)[1].split("\n## ", 1)[0]
    deps = _pkgbuild_array(pkgbuild, "depends") + _pkgbuild_array(pkgbuild, "optdepends")
    assert "python-pyqt6" in deps and "python-cryptography" in deps
    missing = [d for d in deps if not re.search(r"^\| %s( \(optional\))? \|" % re.escape(d), system, re.M)]
    assert not missing, "not in docs/THIRD-PARTY.md, category 4: %s" % missing
    makedeps = _pkgbuild_array(pkgbuild, "makedepends")
    assert makedeps
    missing = [d for d in makedeps if not re.search(r"^\| %s\b" % re.escape(d), build, re.M)]
    assert not missing, "not in docs/THIRD-PARTY.md, category 3: %s" % missing


# --- Rust libraries -----------------------------------------------------------------

def _doc_lists(tool):
    text = doc()
    shipped = text.split(tool.DOC_SHIPPED, 1)[1].split(tool.DOC_BUILD, 1)[0]
    build = text.split(tool.DOC_BUILD, 1)[1]
    row = re.compile(r"^(\S+) v(\S+) — (.+?) — (.+)$", re.M)
    return row.findall(shipped), row.findall(build)


def test_rust_inventory_agrees_with_the_licence_file():
    tool = load("third-party")
    shipped, build = _doc_lists(tool)
    crates = (ROOT / "licenses" / "RUST-CRATES.txt").read_text("utf-8")
    inventory = re.findall(r"^(\S+) (\d\S*)\n  licence:    (.+)\n  copyright:  .+\n  repository: .+\n"
                           r"  source:     (.+)\n  texts:      (.+)\n", crates, re.M)
    assert [(n, v, lic) for n, v, lic, _s, _t in inventory] == [(n, v, lic) for n, v, lic, _r in shipped]
    assert "Inventory (%d libraries)" % len(shipped) in crates
    numbers = set(re.findall(r"^\[(\d+)\] ", crates, re.M))
    for n, v, lic, source, texts in inventory:
        refs = re.findall(r"\[(\d+)\]", texts)
        assert refs and set(refs) <= numbers, (n, texts)
        if n != "ike-adblock":
            assert re.fullmatch(r"https://crates\.io/api/v1/crates/%s/%s/download \(sha256 [0-9a-f]{64}\)"
                                % (re.escape(n), re.escape(v)), source), source
    # every licence named is approved, and every approved one is known to the tool
    allow = tool.approved((ROOT / "ike-adblock" / "deny.toml").read_text("utf-8"))
    for n, v, lic, _r in shipped + build:
        tool.check_approved("%s %s" % (n, v), lic, allow)
    assert {"MIT", "Apache-2.0", "MPL-2.0"} <= {p.stem for p in tool.STANDARD_TEXTS.iterdir()}


def test_rust_standard_library_is_credited():
    crates = (ROOT / "licenses" / "RUST-CRATES.txt").read_text("utf-8")
    assert "The Rust standard library is compiled into the engine" in crates
    assert re.search(r"^Used by: .*the Rust standard library", crates, re.M)


def test_licence_expressions():
    tool = load("third-party")
    assert tool.normalised("MIT/Apache-2.0") == "MIT OR Apache-2.0"
    assert tool.normalised("(MIT OR Apache-2.0) AND Unicode-3.0") == "(MIT OR Apache-2.0) AND Unicode-3.0"
    assert tool.parse("Apache-2.0 WITH LLVM-exception") == "Apache-2.0 WITH LLVM-exception"
    assert tool.parse("MIT OR Apache-2.0 AND Zlib") == ("OR", ["MIT", ("AND", ["Apache-2.0", "Zlib"])])
    for bad in ("", "MIT OR", "(MIT", "MIT Apache-2.0", "AND MIT", "MIT WITH"):
        with pytest.raises(tool.LicenceError):
            tool.parse(bad)
    allow = ["MIT", "Apache-2.0", "Unicode-3.0"]
    tool.check_approved("x", "MIT OR Apache-2.0", allow)
    # an alternative that is not approved is refused as well: a person decides
    for bad in ("MIT OR GPL-2.0-only", "BUSL-1.1", "Apache-2.0 WITH LLVM-exception", "LicenseRef-x"):
        with pytest.raises(tool.LicenceError, match="not approved"):
            tool.check_approved("x", bad, allow)
    tree = tool.parse("(MIT OR Apache-2.0) AND Unicode-3.0")
    assert tool.satisfied(tree, {"Apache-2.0", "Unicode-3.0"})
    assert not tool.satisfied(tree, {"MIT"})
    assert tool.needed(tree, {"MIT"}) == ["Unicode-3.0"]
    assert tool.needed(tool.parse("MIT OR Apache-2.0"), set()) == ["MIT"]
    assert tool.approved('allow = [\n  "MIT", # the usual\n  "Unlicense",\n]\n') == ["MIT", "Unlicense"]
    with pytest.raises(tool.LicenceError):
        tool.approved("[licenses]\n")


def _meta(tmp_path):
    """A fake cargo metadata: an engine with a library, a procedural macro, a
    build dependency and a library only the macro uses."""
    def pkg(name, kind="lib", lic="MIT", files=()):
        d = tmp_path / name
        d.mkdir()
        (d / "Cargo.toml").write_text("")
        for f, text in files:
            (d / f).parent.mkdir(parents=True, exist_ok=True)
            (d / f).write_text(text)
        return {"id": name, "name": name, "version": "1.0.0", "license": lic,
                "manifest_path": str(d / "Cargo.toml"), "targets": [{"kind": [kind]}],
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "repository": "https://x.test/%s/" % name, "authors": ["A Person <a@x.test>"]}
    mit = "MIT License\n\nCopyright (c) 2020 A Person\n\n" \
          "Permission is hereby granted, free of charge, to any person obtaining a copy\nof this software ...\n"
    pkgs = [pkg("engine", "cdylib", "MPL-2.0"), pkg("lib", files=[("LICENSE-MIT", mit),
                                                                 ("data/LICENSE-UNICODE", "UNICODE, INC. ...\n")]),
            pkg("derive", "proc-macro"), pkg("helper"), pkg("buildtool")]
    pkgs[0]["source"] = None
    node = lambda pid, *deps: {"id": pid, "deps": [{"pkg": d, "dep_kinds": [{"kind": k}]} for d, k in deps]}  # noqa
    nodes = [node("engine", ("lib", None), ("derive", None), ("buildtool", "build")),
             node("lib", ("derive", None)), node("derive", ("helper", None)), node("helper"), node("buildtool")]
    return {"packages": pkgs, "resolve": {"root": "engine", "nodes": nodes}}


def test_only_what_is_compiled_in_counts_as_shipped(tmp_path):
    tool = load("third-party")
    shipped, build_only, other = tool.classify(_meta(tmp_path))
    assert shipped == {"engine", "lib"}
    assert build_only == {"derive", "helper", "buildtool"} and other == set()


def test_licence_texts_of_a_crate(tmp_path):
    tool = load("third-party")
    meta = _meta(tmp_path)
    pkgs = {p["id"]: p for p in meta["packages"]}
    entry = tool.crate_entry(pkgs["lib"], ["MIT", "MPL-2.0"], {("lib", "1.0.0"): "ab" * 32})
    assert [f["file"] for f in entry["files"]] == ["LICENSE-MIT", "data/LICENSE-UNICODE"]   # nested ones too
    assert entry["copyright"] == ["Copyright (c) 2020 A Person"]
    assert entry["source"].endswith("/lib/1.0.0/download (sha256 %s)" % ("ab" * 32))
    # a crate without a licence text gets the standard one, and says so
    entry = tool.crate_entry(pkgs["engine"], ["MIT", "MPL-2.0"], {})
    assert entry["files"][0]["file"].startswith("(standard text of MPL-2.0")
    assert "Mozilla Public License Version 2.0" in entry["files"][0]["text"]
    assert entry["copyright"] == ["Copyright (C) 2026 the I.K.E. project"]
    out = tool.render_crates([entry], tool.rust_std_texts())
    assert "engine 1.0.0\n  licence:    MPL-2.0\n" in out and "Used by: the Rust standard library" in out
    # no licence stated, a licence not approved, or one with no text anywhere: an error
    pkgs["helper"]["license"] = None
    with pytest.raises(tool.LicenceError, match="states no licence"):
        tool.crate_entry(pkgs["helper"], ["MIT"], {})
    with pytest.raises(tool.LicenceError, match="not approved"):
        tool.crate_entry(pkgs["lib"], ["MPL-2.0"], {})
    pkgs["derive"]["license"] = "Zlib"
    with pytest.raises(tool.LicenceError, match="no text of Zlib"):
        tool.crate_entry(pkgs["derive"], ["Zlib"], {})


def test_the_check_fails_loudly(tmp_path, monkeypatch, capsys):
    """A crate under a licence nobody approved stops tools/third-party.py."""
    tool = load("third-party")
    meta = _meta(tmp_path)
    meta["packages"][1]["license"] = "SSPL-1.0"
    lock = tmp_path / "Cargo.lock"
    lock.write_text("".join('[[package]]\nname = "%s"\nversion = "1.0.0"\n\n' % p["name"]
                            for p in meta["packages"]))
    monkeypatch.setattr(tool, "LOCK", lock)
    monkeypatch.setattr(tool, "metadata", lambda platform=tool.TARGET: meta)
    assert tool.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "LICENCE CHECK FAILED" in err and "lib 1.0.0: licence SSPL-1.0 not approved" in err
    # and a crate whose licence cannot be read at all
    meta["packages"][1]["license"] = "MIT OR"
    assert tool.main([]) == 1
    assert "cannot read the licence" in capsys.readouterr().err


@pytest.mark.skipif(APP != ROOT, reason="the sources are checked once, not for the installed copy")
def test_generated_files_are_up_to_date():
    """The full check with cargo (GitHub Actions runs it in its own step too)."""
    try:
        subprocess.run(["cargo", "--version"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("cargo is not installed here: GitHub Actions runs this check")
    done = subprocess.run(["python3", str(ROOT / "tools" / "third-party.py"), "--check"],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr


# --- uBlock Origin scriptlets ----------------------------------------------------

def test_ubo_scriptlets_notice():
    tool = load("third-party")
    data = json.loads((ROOT / "ike" / "resources" / "ubo-scriptlets.json").read_text("utf-8"))
    assert data["license"] == "GPL-3.0-or-later"
    assert data["copyright"] == "Copyright (C) Raymond Hill and the uBlock Origin contributors"
    assert data["source"] == "https://github.com/gorhill/uBlock"
    assert re.fullmatch(r"[0-9a-f]{40}", data["commit"]) and re.fullmatch(r"\d{4}-\d\d-\d\d", data["date"])
    notice = (ROOT / "licenses" / "NOTICE.ubo-scriptlets").read_text("utf-8")
    assert notice == tool.render_ubo_notice(data)
    assert data["commit"] in notice and "tools/build-ubo-scriptlets.mjs" in notice
    assert "keep their own licence" in notice
    builder = (ROOT / "tools" / "build-ubo-scriptlets.mjs").read_text("utf-8")
    assert "license: 'GPL-3.0-or-later'" in builder


# --- no list that I.K.E. may not use ------------------------------------------------

def test_withdrawn_list_is_named_only_where_it_is_removed():
    """The list removed in 1.1.18 is named only by the step that removes it
    from old settings, its tests and the history in CHANGELOG.md."""
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    allowed = {"ike/config.py", "tests/test_credits.py", "tests/test_licences.py", "CHANGELOG.md"}
    found = []
    for name in names.decode().split("\0"):
        p = ROOT / name
        if not name or name in allowed or not p.is_file():
            continue
        try:
            text = p.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"pgl\.yoyo|Peter Lowe|pgl_off", text, re.I):
            found.append(name)
    assert not found, found
    config = (ROOT / "ike" / "config.py").read_text("utf-8")
    assert config.count("pgl.yoyo.org") == 1 and "Peter Lowe" not in config
