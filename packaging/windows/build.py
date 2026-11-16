#!/usr/bin/env python3
"""Build I.K.E. for Windows: the folder that gets installed, and its installer.

    python packaging\\windows\\build.py [--out DIR] [--no-installer]

Run on 64-bit Windows with CPython 3.13 (the version of PYTHON_VERSION below),
Rust for MSVC, Visual Studio's C compiler and Inno Setup 6. The Windows
workflow (.github/workflows/windows.yml) is the reference; docs/BUILDING.md
has the steps for a PC.

What it puts together, in DIR\\app (default build\\windows\\app):

    ike-browser.exe        the launcher (launcher/ike-browser.c), with icon and version
    ike_boot.py, ike\\, vendor\\adblock\\ (ike_adblock.pyd), update.json
    python\\               the embeddable CPython from python.org (SHA-256 pinned below)
    python\\Lib\\site-packages\\   the wheels of requirements.txt, each checked
                           against its pinned hash by pip (--require-hashes)
    licenses\\             the licence texts

and DIR\\installer\\ike-browser-<version>-windows-x64-setup.exe (Inno Setup,
ike-browser.iss), with DIR\\build-info.json saying what went in.

Nothing here downloads a codec, and what is not wanted is taken out: Qt
Multimedia and the FFmpeg libraries that belong to it (see PRUNE). The wheels
keep their layout (python\\Lib\\site-packages\\PyQt6\\Qt6\\...): a Qt WebEngine
built elsewhere is put in by replacing the files of the same names (--engine).
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# The embeddable distribution of CPython for 64-bit Windows, from python.org.
# The hash is the one python.org publishes for the file (its SBOM,
# python-<version>-embed-amd64.zip.spdx.json, "SPDXRef-PACKAGE-cpython").
PYTHON_VERSION = "3.13.17"
PYTHON_URL = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PYTHON_VERSION, PYTHON_VERSION)
PYTHON_SHA256 = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"
PYTHON_MAX_BYTES = 64 * 1024 * 1024

# Taken out of the wheels (patterns of paths under site-packages, "/" between
# folders, case ignored).
# - Qt Multimedia and its FFmpeg: I.K.E. does not use Qt Multimedia, and its
#   FFmpeg libraries hold decoders I.K.E. must not ship. Qt WebEngine has its
#   own media code inside Qt6WebEngineCore.dll and does not load these.
# - the ".debug" resource files, which only a debug build of the engine reads.
PRUNE = (
    "PyQt6/Qt6/bin/avcodec-*.dll", "PyQt6/Qt6/bin/avformat-*.dll", "PyQt6/Qt6/bin/avutil-*.dll",
    "PyQt6/Qt6/bin/swresample-*.dll", "PyQt6/Qt6/bin/swscale-*.dll", "PyQt6/Qt6/bin/avfilter-*.dll",
    "PyQt6/Qt6/bin/avdevice-*.dll", "PyQt6/Qt6/bin/postproc-*.dll",
    "PyQt6/Qt6/bin/Qt6Multimedia*.dll", "PyQt6/Qt6/bin/Qt6SpatialAudio*.dll",
    "PyQt6/Qt6/plugins/multimedia/*", "PyQt6/Qt6/qml/QtMultimedia/*",
    "PyQt6/QtMultimedia*.pyd", "PyQt6/QtMultimedia*.pyi", "PyQt6/QtSpatialAudio*.pyd", "PyQt6/QtSpatialAudio*.pyi",
    "PyQt6/bindings/QtMultimedia*/*", "PyQt6/bindings/QtSpatialAudio*/*",
    "PyQt6/Qt6/resources/*.debug.pak", "PyQt6/Qt6/resources/*.debug.bin",
)
# Must not be anywhere in what is installed: decoders I.K.E. does not ship,
# and anything that looks like a private key.
FORBIDDEN = ("avcodec*.dll", "avformat*.dll", "avutil*.dll", "swresample*.dll", "swscale*.dll", "*ffmpeg*.dll",
             "*openh264*.dll", "*libde265*.dll", "*x264*.dll", "*x265*.dll", "*fdk*aac*.dll", "*widevinecdm*",
             "*.key", "*.pem")
# Must be there for the browser to start.
REQUIRED = (
    "ike-browser.exe", "ike_boot.py", "update.json", "ike/__init__.py", "ike/app.py", "ike/winapi.py",
    "vendor/adblock/__init__.py", "vendor/adblock/ike_adblock.pyd",
    "python/python3.dll", "python/python313.dll", "python/python313.zip", "python/python313._pth",
    "python/vcruntime140.dll",
    "python/Lib/site-packages/PyQt6/QtWebEngineCore.pyd",
    "python/Lib/site-packages/PyQt6/Qt6/bin/Qt6WebEngineCore.dll",
    "python/Lib/site-packages/PyQt6/Qt6/bin/QtWebEngineProcess.exe",
    "python/Lib/site-packages/PyQt6/Qt6/bin/Qt6Core.dll",
    "python/Lib/site-packages/PyQt6/Qt6/plugins/platforms/qwindows.dll",
    "python/Lib/site-packages/PyQt6/Qt6/resources/qtwebengine_resources.pak",
    "python/Lib/site-packages/PyQt6/Qt6/resources/icudtl.dat",
    "python/Lib/site-packages/cryptography/__init__.py",
    "licenses/LICENSE.txt",
)


def say(text):
    print("build: " + text, flush=True)


def run(cmd, **kw):
    say(" ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def version():
    text = (ROOT / "ike" / "__init__.py").read_text("utf-8")
    found = re.search(r'__version__\s*=\s*"(\d+(?:\.\d+){1,3})"', text)
    if not found:
        raise SystemExit("build: no version in ike/__init__.py")
    return found.group(1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- Python ---------------------------------------------------------------------

def fetch_python(work):
    """The embeddable CPython, downloaded once and always checked."""
    target = work / ("python-%s-embed-amd64.zip" % PYTHON_VERSION)
    if not target.exists():
        say("downloading " + PYTHON_URL)
        req = urllib.request.Request(PYTHON_URL, headers={"User-Agent": "IKE-Browser-build"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read(PYTHON_MAX_BYTES + 1)
        if len(data) > PYTHON_MAX_BYTES:
            raise SystemExit("build: the Python download is unexpectedly large")
        target.write_bytes(data)
    got = sha256(target)
    if got != PYTHON_SHA256:
        target.unlink()
        raise SystemExit("build: python-%s-embed-amd64.zip has SHA-256 %s, expected %s"
                         % (PYTHON_VERSION, got, PYTHON_SHA256))
    say("python-%s-embed-amd64.zip: SHA-256 as pinned" % PYTHON_VERSION)
    return target


def safe_unzip(archive, target):
    """Unpack an archive whose names must all stay inside the target folder."""
    target = target.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            dest = (target / info.filename).resolve()
            if target != dest and target not in dest.parents:
                raise SystemExit("build: %s holds a name that leaves its folder: %s" % (archive.name, info.filename))
        z.extractall(target)


def pth_text(tag):
    """python3XX._pth: the only places this Python loads modules from. With
    this file Python also ignores PYTHONPATH, PYTHONHOME and the user's own
    site-packages: nothing outside the installation is imported."""
    return "python%s.zip\n.\nLib\\site-packages\n" % tag


def install_python(embed_zip, app):
    python = app / "python"
    safe_unzip(embed_zip, python)
    tag = "".join(PYTHON_VERSION.split(".")[:2])
    (python / ("python%s._pth" % tag)).write_text(pth_text(tag), "ascii")
    (python / "Lib" / "site-packages").mkdir(parents=True)
    return python


def install_wheels(python):
    if sys.version_info[:2] != tuple(int(x) for x in PYTHON_VERSION.split(".")[:2]) or sys.maxsize < 2 ** 32:
        raise SystemExit("build: run this with 64-bit CPython %s (the wheels are chosen for the Python that runs pip)"
                         % ".".join(PYTHON_VERSION.split(".")[:2]))
    site = python / "Lib" / "site-packages"
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
         "--require-hashes", "--only-binary=:all:", "--no-deps", "--no-compile",
         "--target", site, "-r", HERE / "requirements.txt"])
    shutil.rmtree(site / "bin", ignore_errors=True)      # console scripts of the packages: not used
    return site


def prune(site):
    removed = []
    for path in sorted(site.rglob("*"), reverse=True):
        rel = path.relative_to(site).as_posix().lower()
        if any(fnmatch.fnmatch(rel, pattern.lower()) for pattern in PRUNE):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(rel)
    for folder in sorted((p for p in site.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return removed


def replace_engine(site, engine):
    """--engine DIR: files of a Qt WebEngine built elsewhere, laid out like
    the wheel (PyQt6/Qt6/bin/Qt6WebEngineCore.dll, PyQt6/Qt6/resources/...).
    Only files that already exist in the wheel are replaced: the build cannot
    be used to add something else to the installer."""
    replaced = []
    for src in sorted(p for p in engine.rglob("*") if p.is_file()):
        rel = src.relative_to(engine)
        dest = site / rel
        if not dest.is_file():
            raise SystemExit("build: --engine has %s, which the wheels do not have" % rel.as_posix())
        shutil.copyfile(src, dest)
        replaced.append({"file": rel.as_posix(), "sha256": sha256(dest)})
    if not replaced:
        raise SystemExit("build: --engine holds no files")
    return replaced


# ---- I.K.E. itself -----------------------------------------------------------------

def copy_app(app, engine_module):
    shutil.copytree(ROOT / "ike", app / "ike", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(ROOT / "ike_boot.py", app / "ike_boot.py")
    shutil.copyfile(ROOT / "data" / "update.json", app / "update.json")
    vendor = app / "vendor" / "adblock"
    vendor.mkdir(parents=True)
    for name in ("__init__.py", "adblock.pyi", "py.typed"):
        shutil.copyfile(ROOT / "vendor" / "adblock" / name, vendor / name)
    shutil.copyfile(engine_module, vendor / "ike_adblock.pyd")
    lic = app / "licenses"
    lic.mkdir()
    shutil.copyfile(ROOT / "LICENSE", lic / "LICENSE.txt")
    for src in sorted((ROOT / "licenses").iterdir()):
        if src.is_file():
            shutil.copyfile(src, lic / src.name)
    shutil.copyfile(ROOT / "docs" / "THIRD-PARTY.md", lic / "THIRD-PARTY.md")
    shutil.copyfile(HERE / "LICENSES-WINDOWS.md", lic / "LICENSES-WINDOWS.md")
    python_licence = app / "python" / "LICENSE.txt"
    if python_licence.exists():
        shutil.copyfile(python_licence, lic / "Python-LICENSE.txt")


def build_engine_module(work):
    """The AdBlock engine with Rust for MSVC: ike_adblock.dll, installed as
    ike_adblock.pyd (the name Python loads on Windows)."""
    target = work / "cargo-target"
    run(["cargo", "build", "--release", "--locked", "--manifest-path", ROOT / "ike-adblock" / "Cargo.toml",
         "--target-dir", target])
    module = target / "release" / "ike_adblock.dll"
    if not module.is_file():
        raise SystemExit("build: cargo did not produce ike_adblock.dll")
    return module


# ---- launcher --------------------------------------------------------------------

def make_icon(target):
    """ike-browser.ico from the project's own PNG icons: the sizes Windows
    asks for (16 to 256), the small ones scaled down from the 256-pixel one."""
    import struct

    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage
    big = QImage(str(ROOT / "data" / "icons" / "ike-browser-256.png"))
    if big.isNull():
        raise SystemExit("build: cannot read data/icons/ike-browser-256.png")
    images = []
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        own = ROOT / "data" / "icons" / ("ike-browser-%d.png" % size)
        image = QImage(str(own)) if own.exists() else big.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if image.width() != size or image.height() != size:
            image = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.convertToFormat(QImage.Format.Format_ARGB32).save(buf, "PNG")
        buf.close()
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, body = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        body += data
    target.write_bytes(header + entries + body)


def vcvars():
    """Visual Studio's "vcvars64.bat" (sets up the C compiler), found with vswhere."""
    base = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(base) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        raise SystemExit("build: Visual Studio (vswhere.exe) not found")
    found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                           capture_output=True, text=True, check=True).stdout.strip().splitlines()
    if not found:
        raise SystemExit("build: no Visual Studio with the C++ tools found")
    script = Path(found[0]) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not script.exists():
        raise SystemExit("build: %s not found" % script)
    return script


def build_launcher(work, app, ver):
    src = work / "launcher"
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(HERE / "launcher", src)
    make_icon(src / "ike-browser.ico")
    parts = (ver.split(".") + ["0", "0", "0"])[:4]
    rc = (src / "ike-browser.rc.in").read_text("utf-8")
    (src / "ike-browser.rc").write_text(
        rc.replace("@VERSION_COMMAS@", ",".join(parts)).replace("@VERSION@", ver), "utf-8")
    script = src / "build.cmd"
    script.write_text("\r\n".join([
        "@echo off",
        'call "%s" >nul || exit /b 1' % vcvars(),
        "rc /nologo /fo ike-browser.res ike-browser.rc || exit /b 1",
        "cl /nologo /O2 /W4 /MT /GS /guard:cf /DUNICODE /D_UNICODE ike-browser.c ike-browser.res "
        "/Fe:ike-browser.exe /link /SUBSYSTEM:WINDOWS /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /guard:cf "
        "/MANIFEST:EMBED /MANIFESTINPUT:ike-browser.exe.manifest || exit /b 1",
        ""]), "ascii")
    run(["cmd", "/d", "/c", script.name], cwd=str(src))
    shutil.copyfile(src / "ike-browser.exe", app / "ike-browser.exe")
    shutil.copyfile(src / "ike-browser.ico", work / "ike-browser.ico")


# ---- checks, installer ------------------------------------------------------------

def check_tree(app):
    missing = [name for name in REQUIRED if not (app / name).is_file()]
    if missing:
        raise SystemExit("build: missing from the installation folder: " + ", ".join(missing))
    bad = sorted(p.relative_to(app).as_posix() for p in app.rglob("*")
                 if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pattern) for pattern in FORBIDDEN))
    if bad:
        raise SystemExit("build: must not be shipped: " + ", ".join(bad))


def compile_python(app):
    """Byte-compile what the installer carries, so nothing is written into
    the installation folder when I.K.E. runs ("unchecked": the compiled file
    is used as it is; the installed sources never change)."""
    run([sys.executable, "-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash",
         app / "ike", app / "vendor", app / "ike_boot.py", app / "python" / "Lib" / "site-packages"])


def iscc():
    for candidate in (shutil.which("ISCC"), shutil.which("iscc"),
                      os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
                      os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe")):
        if candidate and os.path.isfile(candidate):
            return candidate
    raise SystemExit("build: Inno Setup 6 (ISCC.exe) not found")


def build_installer(out, app, work, ver):
    target = out / "installer"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    run([iscc(), "/Qp", "/DAppVersion=" + ver, "/DSourceDir=" + str(app), "/DOutputDir=" + str(target),
         "/DIconFile=" + str(work / "ike-browser.ico"), "/DLicenseFile=" + str(ROOT / "LICENSE"),
         HERE / "ike-browser.iss"])
    setup = target / ("ike-browser-%s-windows-x64-setup.exe" % ver)
    if not setup.is_file():
        raise SystemExit("build: Inno Setup did not produce " + setup.name)
    return setup


def tree_size(folder):
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "build" / "windows"))
    ap.add_argument("--engine-module", help="an ike_adblock.dll / .pyd built before (skips cargo)")
    ap.add_argument("--engine", help="folder with Qt WebEngine files that replace the wheel's (same layout)")
    ap.add_argument("--no-installer", action="store_true", help="only the folder, no setup program")
    args = ap.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("build: this builds the Windows version and runs on Windows only")

    ver = version()
    out = Path(args.out).resolve()
    work, app = out / "work", out / "app"
    shutil.rmtree(app, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    app.mkdir(parents=True)
    say("I.K.E. %s for Windows x64 -> %s" % (ver, out))

    python = install_python(fetch_python(work), app)
    site = install_wheels(python)
    removed = prune(site)
    say("taken out of the wheels: %d files (Qt Multimedia, its FFmpeg, debug resources)" % len(removed))
    replaced = replace_engine(site, Path(args.engine).resolve()) if args.engine else []
    module = Path(args.engine_module).resolve() if args.engine_module else build_engine_module(work)
    copy_app(app, module)
    build_launcher(work, app, ver)
    check_tree(app)
    compile_python(app)
    check_tree(app)

    packages = sorted(d.name[:-len(".dist-info")] for d in site.glob("*.dist-info"))
    info = {
        "ike": ver,
        "python": {"version": PYTHON_VERSION, "url": PYTHON_URL, "sha256": PYTHON_SHA256},
        "packages": packages,
        "requirements_sha256": sha256(HERE / "requirements.txt"),
        "engine": "official Qt WebEngine from PyPI (no H.264 / AAC decoder)" if not replaced else "replaced files",
        "engine_replaced": replaced,
        "removed_from_wheels": removed,
        "launcher_sha256": sha256(app / "ike-browser.exe"),
        "adblock_module_sha256": sha256(app / "vendor" / "adblock" / "ike_adblock.pyd"),
        "installed_bytes": tree_size(app),
        "commit": os.environ.get("GITHUB_SHA", ""),
    }
    if not args.no_installer:
        setup = build_installer(out, app, work, ver)
        info["installer"] = {"file": setup.name, "bytes": setup.stat().st_size, "sha256": sha256(setup)}
        say("%s: %.1f MiB, SHA-256 %s" % (setup.name, setup.stat().st_size / 2 ** 20, info["installer"]["sha256"]))
    (out / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", "utf-8")
    say("installation folder: %.1f MiB in %s" % (info["installed_bytes"] / 2 ** 20, app))
    return 0


if __name__ == "__main__":
    sys.exit(main())
