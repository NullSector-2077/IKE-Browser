#!/usr/bin/env python3
"""Builds I.K.E.'s Qt WebEngine for Windows on a GitHub Actions runner.

Only Qt WebEngine is built, against the official Qt binaries, with the patches
in ``patches/``: H.264 and AAC are decoded by Windows (Media Foundation), and
the engine contains no decoder for them. See README.md in this folder.

The build is far longer than one job may last, so it is done in stages. Each
stage restores the build folder of the stage before, builds until its time is
up, and saves the folder again. For that to work every path is the same in
every stage (``C:\\q`` by default) and the source files keep fixed dates, so
that Ninja sees nothing to do for what is already built.

    python build.py prepare      tools, Qt, sources
    python build.py restore      the build folder of the stage (or run) before
    python build.py patch        apply patches/, date the source files
    python build.py configure    CMake (skipped when already configured)
    python build.py smoke        compile the patched media code first
    python build.py build        build until done or until the time is up
    python build.py pack         save the build folder for the next stage
    python build.py install      install into a staging folder
    python build.py evidence     what was built in: GN arguments, link inputs
    python build.py package      files laid out as in the PyPI wheel, SHA-256

Run on Windows only. Nothing here is shipped to users.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = json.loads((HERE / "versions.json").read_text(encoding="utf-8"))

ROOT = Path(os.environ.get("IKE_ENGINE_ROOT", r"C:\q"))
SRC = ROOT / "s"                 # qtwebengine, with Chromium in src/3rdparty
BUILD = ROOT / "b"               # the build folder, carried from stage to stage
QT_ROOT = ROOT / "qt"            # official Qt binaries
TOOLS = ROOT / "t"               # flex, bison, gperf
INSTALL = ROOT / "i"             # cmake --install
OUT = ROOT / "out"               # what the workflow uploads
STATE = BUILD / "ike-engine-state.json"

QT_PREFIX = QT_ROOT / VERSIONS["qt_version"] / VERSIONS["qt_dir"]

# Source files get this date (2026-01-01 UTC) in every stage. A file whose
# content changed since the build folder last saw it gets the current time.
FIXED_MTIME = 1767225600

# A decoder or encoder for H.264 / AAC must never be linked in. These names are
# searched in everything the linker is given and in the linker's map.
FORBIDDEN_SYMBOLS = (
    "ff_h264_decoder",
    "ff_aac_decoder",
    "ff_aac_fixed_decoder",
    "ff_aac_latm_decoder",
    "ff_hevc_decoder",
    "WelsCreateDecoder",
    "WelsCreateSVCEncoder",
    "WelsDestroyDecoder",
    "WelsDestroySVCEncoder",
)
# Reported, not forbidden: they read a stream's headers and decode nothing.
REPORTED_SYMBOLS = ("ff_h264_parser", "ff_aac_parser", "ff_aac_demuxer")
# Free codecs that must be found, to show that the search sees FFmpeg at all.
EXPECTED_SYMBOLS = ("ff_flac_decoder", "ff_vorbis_decoder", "ff_mov_demuxer")
# Text that only the decoders / encoders themselves contain.
FORBIDDEN_STRINGS = (
    b"no frame!",                                       # FFmpeg h264dec.c
    b"mmco: unref short failure",                       # FFmpeg h264_refs.c
    b"Frame num change from",                           # FFmpeg h264_slice.c
    b"Input buffer exhausted before END element found", # FFmpeg aacdec
    b"channel element %d.%d is not allocated",          # FFmpeg aacdec
    b"invalid band type",                               # FFmpeg aacdec
    b"WelsCreateSVCEncoder",                            # OpenH264
    b"WelsCreateDecoder",                               # OpenH264
    b"CWelsH264SVCEncoder",                             # OpenH264
    b"WelsInitEncoderExt",                              # OpenH264
)
# Text that must be there: the Windows paths and one free decoder.
EXPECTED_STRINGS = (
    b"MediaFoundationVideoDecoder",
    b"MediaFoundationAudioDecoder",
    b"D3D11VideoDecoder",
    b"VpxVideoDecoder",
    b"Dav1dVideoDecoder",
)


def log(message):
    print(f"[engine] {message}", flush=True)


def run(cmd, cwd=None, env=None, check=True):
    shown = " ".join(str(c) for c in cmd)
    log(f"$ {shown}" + (f"   (in {cwd})" if cwd else ""))
    result = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed with code {result.returncode}: {shown}")
    return result.returncode


def output(cmd, cwd=None, env=None):
    return subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def free_gb(path):
    probe = Path(path)
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free / 2 ** 30


def set_output(name, value):
    target = os.environ.get("GITHUB_OUTPUT")
    log(f"output {name}={value}")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def note(text):
    """A note attached to the job; readable from outside while the job runs."""
    print(f"::notice title=Engine build, stage {os.environ.get('IKE_STAGE', '?')}::{text[:300]}",
          flush=True)


def summary(text):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n")


# --- the compiler's environment ---------------------------------------------

def msvc_env():
    """The process environment plus what vcvars64.bat adds."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) \
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    install = output([vswhere, "-latest", "-products", "*", "-requires",
                      "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                      "-property", "installationPath"]).strip().splitlines()[0]
    vcvars = Path(install) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    dumped = subprocess.run(f'cmd /s /c ""{vcvars}" >nul 2>&1 && set"', check=True,
                            capture_output=True, text=True, shell=False).stdout
    env = {}
    for line in dumped.splitlines():
        if "=" in line and not line.startswith("="):
            key, _, value = line.partition("=")
            env[key] = value
    if "VCToolsVersion" not in env:
        raise SystemExit(f"vcvars64.bat did not set up the compiler ({vcvars})")
    return env


def build_env():
    env = msvc_env()
    path = [str(QT_PREFIX / "bin"), str(TOOLS / "gnuwin32" / "bin"),
            str(Path(sys.executable).parent)]
    env["PATH"] = os.pathsep.join(path + [env.get("PATH", "")])
    # Read by Qt WebEngine's CMake files when they configure: the flags of the
    # Ninja that builds Chromium. Four jobs on four cores; more runs out of
    # memory with MSVC.
    env["NINJAFLAGS"] = os.environ.get("IKE_NINJAFLAGS", "-j4")
    # Read by the Microsoft linker: write a map of every symbol linked in, the
    # evidence for the "no H.264 / AAC decoder" check.
    env["LINK"] = "/MAP"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# --- prepare ----------------------------------------------------------------

def report_machine():
    log(f"runner image: {os.environ.get('ImageOS', '?')} {os.environ.get('ImageVersion', '?')}")
    log(f"processors: {os.cpu_count()}")
    for drive in ("C:\\", "D:\\"):
        if Path(drive).exists():
            usage = shutil.disk_usage(drive)
            log(f"disk {drive} free {usage.free / 2**30:.1f} GB of {usage.total / 2**30:.1f} GB")
    for tool in (["cmake", "--version"], ["ninja", "--version"], ["node", "--version"],
                 ["git", "--version"], ["7z", "i"]):
        try:
            first = output(tool).strip().splitlines()
            log(f"{tool[0]}: {next((l for l in first if l.strip()), '?')}")
        except (OSError, subprocess.CalledProcessError) as error:
            log(f"{tool[0]}: NOT FOUND ({error})")
    log(f"python: {sys.version.split()[0]} at {sys.executable}")


def download(url, target=None, tries=4):
    """The bytes at |url| (or written to |target|), with a few retries."""
    last = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ike-engine-build"})
            with urllib.request.urlopen(request, timeout=120) as reply:
                if target is None:
                    return reply.read()
                with open(target, "wb") as handle:
                    shutil.copyfileobj(reply, handle, 1 << 20)
                return None
        except OSError as error:
            last = error
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"could not download {url}: {last}")


def qt_repository():
    """(base URL, parsed Updates.xml) of the official Qt binaries wanted.

    Qt's online repository changed its layout more than once; the folder for
    one compiler is looked for under the names used so far."""
    import xml.etree.ElementTree as ElementTree
    code = VERSIONS["qt_version"].replace(".", "")
    root = f"{VERSIONS['qt_repository']}/qt6_{code}"
    tried = []
    for folder in (f"qt6_{code}_{VERSIONS['qt_dir']}", f"qt6_{code}_{VERSIONS['qt_arch']}",
                   f"qt6_{code}"):
        url = f"{root}/{folder}/Updates.xml"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ike-engine-build"})
            with urllib.request.urlopen(request, timeout=60) as reply:
                data = reply.read()
        except OSError as error:
            tried.append(f"{url}: {error}")
            continue
        log(f"Qt repository: {url} ({len(data):,} bytes)")
        return f"{root}/{folder}", ElementTree.fromstring(data)
    for line in tried:
        log(line)
    try:
        listing = download(root + "/", tries=1).decode("utf-8", "replace")
        log("folders there: " + " ".join(sorted(set(re.findall(r'href="([^"?/]+)/"', listing)))))
    except SystemExit as error:
        log(str(error))
    raise SystemExit("the official Qt binaries were not found in the online repository")


def install_qt():
    """The official Qt binaries, the same that the PyPI wheels repackage:
    read from Qt's online repository, checked against its SHA-1 files."""
    if (QT_PREFIX / "bin" / "qt-cmake.bat").exists():
        log(f"Qt already at {QT_PREFIX}")
        return
    base, updates = qt_repository()
    code = VERSIONS["qt_version"].replace(".", "")
    arch = VERSIONS["qt_arch"]
    wanted = {f"qt.qt6.{code}.{arch}": "base"}
    for module in VERSIONS["qt_modules"]:
        wanted[f"qt.qt6.{code}.addons.{module}.{arch}"] = module
    packages = {}
    for package in updates.iter("PackageUpdate"):
        name = package.findtext("Name", "")
        if name in wanted:
            archives = [a.strip() for a in package.findtext("DownloadableArchives", "").split(",")
                        if a.strip()]
            packages[name] = (package.findtext("Version", ""), archives)
    missing = [name for name in wanted if name not in packages]
    if missing:
        names = sorted(p.findtext("Name", "") for p in updates.iter("PackageUpdate"))
        log("packages offered: " + " ".join(n for n in names if "debug_information" not in n))
        raise SystemExit(f"not in the Qt repository: {missing}")
    QT_ROOT.mkdir(parents=True, exist_ok=True)
    scratch = QT_ROOT / "dl"
    scratch.mkdir(exist_ok=True)
    for name, (version, archives) in packages.items():
        for archive in archives:
            url = f"{base}/{name}/{version}{archive}"
            target = scratch / archive
            download(url, target)
            expected = download(url + ".sha1").decode("ascii", "replace").split()[0]
            actual = hashlib.sha1(target.read_bytes()).hexdigest()
            log(f"{archive}: {target.stat().st_size / 2**20:.1f} MB, sha1 {actual}, "
                f"sha256 {sha256_file(target)}")
            if actual != expected:
                raise SystemExit(f"{archive}: SHA-1 is {actual}, the repository says {expected}")
            # The archives hold the content of <version>/<compiler>/ itself
            # (bin, lib, ...); Qt's installer puts them there.
            listing = output(["7z", "l", "-ba", "-slt", target])
            inside = re.findall(r"^Path = (.+)$", listing, flags=re.M)
            nested = any(p.replace("\\", "/").startswith(VERSIONS["qt_version"] + "/")
                         for p in inside)
            where = QT_ROOT if nested else QT_PREFIX
            where.mkdir(parents=True, exist_ok=True)
            run(["7z", "x", target, f"-o{where}", "-y", "-bso0", "-bsp0"])
            target.unlink()
    shutil.rmtree(scratch, ignore_errors=True)
    if not (QT_PREFIX / "bin" / "qt-cmake.bat").exists():
        found = [str(p) for p in QT_ROOT.glob("*/*/*")][:20]
        raise SystemExit(f"Qt was unpacked but {QT_PREFIX} has no qt-cmake.bat; found {found}")
    for library in ("Qt6Core.dll", "Qt6Quick.dll", "Qt6WebChannel.dll", "Qt6Positioning.dll"):
        log(f"{library}: {'present' if (QT_PREFIX / 'bin' / library).exists() else 'MISSING'}")


def install_gnuwin32():
    """flex, bison and gperf, the build Qt's own CI uses."""
    target = TOOLS / "gnuwin32" / "bin"
    if (target / "gperf.exe").exists():
        return
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / "gnuwin32.zip"
    log(f"downloading {VERSIONS['gnuwin32_url']}")
    download(VERSIONS["gnuwin32_url"], archive)
    sha1 = hashlib.sha1(archive.read_bytes()).hexdigest()
    log(f"gnuwin32.zip sha1 {sha1} sha256 {sha256_file(archive)}")
    if sha1 != VERSIONS["gnuwin32_sha1"]:
        raise SystemExit("gnuwin32.zip does not have the checksum Qt's CI expects")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(TOOLS)
    archive.unlink()
    for tool in ("gperf.exe", "bison.exe", "flex.exe"):
        if not (target / tool).exists():
            raise SystemExit(f"{tool} is not in gnuwin32.zip where expected ({target})")


def git(*args, cwd=None, check=True):
    return run(["git", "-c", "core.autocrlf=false", "-c", "core.longpaths=true",
                "-c", "advice.detachedHead=false", *args], cwd=cwd, check=check)


def fetch_commit(folder, repo, commit):
    """A shallow checkout of exactly |commit|."""
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".git").exists():
        git("init", "-q", cwd=folder)
        git("remote", "add", "origin", repo, cwd=folder)
    git("fetch", "-q", "--depth", "1", "origin", commit, cwd=folder)
    git("checkout", "-q", "--force", "FETCH_HEAD", cwd=folder)
    head = output(["git", "rev-parse", "HEAD"], cwd=folder).strip()
    if head != commit:
        raise SystemExit(f"{folder}: got {head}, wanted {commit}")


def fetch_sources():
    marker = SRC / ".ike-sources"
    wanted = VERSIONS["qtwebengine_commit"] + " " + VERSIONS["chromium_commit"]
    if marker.exists() and marker.read_text().strip() == wanted:
        log("sources already fetched")
        return
    if SRC.exists():
        shutil.rmtree(SRC, ignore_errors=True)
    fetch_commit(SRC, VERSIONS["qtwebengine_repo"], VERSIONS["qtwebengine_commit"])
    recorded = output(["git", "ls-tree", "HEAD", "src/3rdparty"], cwd=SRC).split()[2]
    if recorded != VERSIONS["chromium_commit"]:
        raise SystemExit(f"qtwebengine pins Chromium {recorded}, versions.json says "
                         f"{VERSIONS['chromium_commit']}")
    fetch_commit(SRC / "src" / "3rdparty", VERSIONS["chromium_repo"], VERSIONS["chromium_commit"])
    marker.write_text(wanted + "\n")


def patch_files():
    return (sorted((HERE / "patches" / "qtwebengine").glob("*.patch")),
            sorted((HERE / "patches" / "chromium").glob("*.patch")))


def patched_paths(patch, base):
    paths = []
    for line in patch.read_text(encoding="utf-8").splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            paths.append(base / line[6:])
    return paths


def apply_patches():
    """Applies the patches to pristine sources. Returns the files they touch."""
    qt_patches, chromium_patches = patch_files()
    if not qt_patches or not chromium_patches:
        raise SystemExit("no patches found next to build.py")
    chromium = SRC / "src" / "3rdparty"
    touched = []
    for folder, patches in ((SRC, qt_patches), (chromium, chromium_patches)):
        # Back to the pristine tree first, so a changed patch set applies too.
        git("checkout", "-q", "--force", "HEAD", "--", ".", cwd=folder)
        for patch in patches:
            for path in patched_paths(patch, folder):
                tracked = subprocess.run(["git", "ls-files", "--error-unmatch",
                                          str(path.relative_to(folder)).replace("\\", "/")],
                                         cwd=folder, capture_output=True).returncode == 0
                if not tracked and path.exists():
                    path.unlink()        # a file an earlier patch set added
        for patch in patches:
            git("apply", "--whitespace=nowarn", "--verbose", str(patch), cwd=folder)
            touched += patched_paths(patch, folder)
    touched = sorted({p for p in touched if p.exists()})
    log(f"{len(qt_patches) + len(chromium_patches)} patches applied, {len(touched)} files touched")
    return touched


def normalise_dates(touched):
    """Gives every source file the fixed date, and the current time to patched
    files whose content the build folder has not seen yet."""
    started = time.time()
    count = 0
    for folder, dirs, files in os.walk(SRC):
        if ".git" in dirs:
            dirs.remove(".git")
        for name in files:
            try:
                os.utime(os.path.join(folder, name), (FIXED_MTIME, FIXED_MTIME))
                count += 1
            except OSError:
                pass
    log(f"{count} source files dated in {time.time() - started:.0f} s")

    seen = {}
    if STATE.exists():
        try:
            seen = json.loads(STATE.read_text(encoding="utf-8")).get("patched", {})
        except ValueError:
            seen = {}
    now = time.time()
    current = {}
    for path in touched:
        key = str(path.relative_to(SRC)).replace("\\", "/")
        current[key] = sha256_file(path)
        if seen.get(key) != current[key]:
            os.utime(path, (now, now))
            log(f"  changed since the last build: {key}")
    # A file that was patched before and no longer is has changed as well.
    for key in seen:
        path = SRC / key
        if key not in current and path.exists():
            os.utime(path, (now, now))
            log(f"  no longer patched: {key}")
    return current


def save_state(patched):
    BUILD.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"patched": patched, "versions": VERSIONS}, indent=1),
                     encoding="utf-8")


def cmd_prepare(_args):
    report_machine()
    ROOT.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "html5lib"])
    install_gnuwin32()
    install_qt()
    fetch_sources()
    log(f"free space after preparing: {free_gb(ROOT):.1f} GB")
    env = msvc_env()
    log(f"MSVC {env.get('VCToolsVersion')}, Windows SDK {env.get('WindowsSDKVersion')}, "
        f"Visual Studio {env.get('VisualStudioVersion')}")
    note(f"prepared: MSVC {env.get('VCToolsVersion')}, SDK {env.get('WindowsSDKVersion')}, "
         f"{free_gb(ROOT):.0f} GB free, image {os.environ.get('ImageVersion', '?')}")


def cmd_patch(_args):
    """After the build folder of the stage before is restored: patch the
    sources and date them against what that folder has seen."""
    touched = apply_patches()
    patched = normalise_dates(touched)
    save_state(patched)


# --- the build folder, from stage to stage ------------------------------------

TREE_ARTIFACT = "engine-build-tree"
TREE_KEYS = ("qtwebengine_commit", "chromium_commit", "qt_version", "qt_arch")


def find_earlier_run():
    """The newest run of this repository that kept a build folder."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    this_run = os.environ.get("GITHUB_RUN_ID", "")
    listed = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/artifacts?name={TREE_ARTIFACT}&per_page=30"],
        capture_output=True, text=True)
    if listed.returncode != 0:
        log(f"could not list earlier build folders: {listed.stderr.strip()[:300]}")
        return None
    artifacts = [a for a in json.loads(listed.stdout).get("artifacts", [])
                 if not a.get("expired") and str(a.get("workflow_run", {}).get("id")) != this_run]
    artifacts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    for artifact in artifacts:
        run_id = artifact.get("workflow_run", {}).get("id")
        log(f"earlier build folder: run {run_id}, {artifact.get('created_at')}, "
            f"{artifact.get('size_in_bytes', 0) / 2**30:.1f} GB, "
            f"branch {artifact.get('workflow_run', {}).get('head_branch')}")
        return str(run_id)
    log("no earlier build folder to continue from")
    return None


def cmd_restore(args):
    """Unpacks the build folder that the stage before saved. In the first
    stage: the one of an earlier run (``auto``, a run id) or none."""
    download = ROOT / "dl"
    if not any(download.glob("build-tree.7z.*")) and args.source != "none":
        run_id = find_earlier_run() if args.source == "auto" else args.source
        if run_id:
            code = run(["gh", "run", "download", run_id, "--repo",
                        os.environ.get("GITHUB_REPOSITORY", ""), "-n", TREE_ARTIFACT,
                        "-D", download], check=False)
            if code != 0:
                log("the earlier build folder could not be downloaded; starting empty")
    first = download / "build-tree.7z.001"
    if not first.exists():
        log("no build folder to restore: this stage starts from nothing")
        note("no build folder restored: starting from nothing")
        return
    if BUILD.exists():
        shutil.rmtree(BUILD)
    started = time.time()
    run(["7z", "x", first, f"-o{ROOT}", "-y", "-bso0", "-bsp0"])
    shutil.rmtree(download, ignore_errors=True)
    log(f"build folder restored in {time.time() - started:.0f} s, "
        f"free space {free_gb(ROOT):.1f} GB")
    note(f"build folder restored in {time.time() - started:.0f} s")
    seen = {}
    if STATE.exists():
        try:
            seen = json.loads(STATE.read_text(encoding="utf-8")).get("versions", {})
        except ValueError:
            pass
    different = [key for key in TREE_KEYS if seen.get(key) != VERSIONS[key]]
    if different:
        log(f"the restored build folder is for other versions ({different}): not used")
        shutil.rmtree(BUILD, ignore_errors=True)


def cmd_pack(_args):
    """Packs the build folder for the next stage, in pieces of 1.9 GB."""
    if not (BUILD / "CMakeCache.txt").exists():
        log("no configured build folder to save")
        set_output("packed", "false")
        return
    target = OUT / "tree"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    started = time.time()
    run(["7z", "a", "-t7z", "-mx=1", "-mmt=on", "-v1900m", "-bso0", "-bsp0",
         target / "build-tree.7z", BUILD.name], cwd=ROOT)
    size = sum(p.stat().st_size for p in target.iterdir())
    log(f"build folder packed: {size / 2**30:.2f} GB in {time.time() - started:.0f} s")
    summary(f"- build folder saved: {size / 2**30:.2f} GB")
    note(f"build folder saved: {size / 2**30:.2f} GB")
    set_output("packed", "true")


# --- configure --------------------------------------------------------------

def cmd_configure(_args):
    env = build_env()
    if (BUILD / "CMakeCache.txt").exists() and (BUILD / "build.ninja").exists():
        log("already configured; CMake runs again by itself if its files changed")
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    # qt-cmake.bat and not qt-cmake-private.bat: the latter forces the generator
    # Qt itself was built with ("Ninja Multi-Config", release and debug). One
    # release configuration is all that is wanted here, and all that fits.
    qt_cmake = QT_PREFIX / "bin" / "qt-cmake.bat"
    run([qt_cmake, "-G", "Ninja", "-S", SRC, "-B", BUILD,
         "-DCMAKE_BUILD_TYPE=Release",
         "-DQT_USE_ORIGINAL_COMPILER=ON",
         "-DQT_GENERATE_SBOM=OFF",
         # Formats known, decoders left to Windows: see patches/README.md.
         "-DFEATURE_webengine_proprietary_codecs=ON",
         # Qt PDF is a separate module that PyQt6-WebEngine does not contain.
         "-DFEATURE_qtpdf_build=OFF",
         # As the official build: Chromium 140 needs no Rust.
         "-DFEATURE_webengine_rust_build=OFF",
         "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF",
         f"-DPython3_EXECUTABLE={Path(sys.executable).as_posix()}"],
        env=env)


def gn_dir():
    found = sorted(BUILD.glob("src/core/*/*/args.gn"))
    if not found:
        return None
    return found[0].parent


def check_gn_args(folder):
    text = (folder / "args.gn").read_text(encoding="utf-8")
    values = dict(re.findall(r"^\s*([a-z0-9_]+)\s*=\s*(\S+)\s*$", text, flags=re.M))
    wanted = {
        "proprietary_codecs": "true",
        "ffmpeg_branding": '"Chromium"',
        "media_use_openh264": "false",
        "rtc_use_h264": "false",
        "enable_hevc_parser_and_hw_decoder": "false",
        "is_debug": "false",
        "symbol_level": "0",
    }
    bad = {k: values.get(k) for k, v in wanted.items() if values.get(k) != v}
    for key in wanted:
        log(f"  args.gn {key} = {values.get(key)}")
    if bad:
        raise SystemExit(f"args.gn does not have the wanted values: {bad}")


# --- smoke ------------------------------------------------------------------

SMOKE_PATTERN = re.compile(
    r"^(obj/media/(base|filters|renderers|ffmpeg|formats|parsers|video|mojo/services|"
    r"mojo/clients|gpu|cdm)/[^:]*\.obj): ")


def cmd_smoke(_args):
    """Runs GN, then compiles the media code before anything else, so that a
    mistake in the patches shows in minutes and not after hours."""
    env = build_env()
    targets = output(["ninja", "-C", BUILD, "-t", "targets", "all"], env=env)
    gn_targets = sorted(set(re.findall(r"^(runGn_core_[A-Za-z0-9_]+): ", targets, flags=re.M)))
    if not gn_targets:
        raise SystemExit("no runGn_core_* target in the CMake build")
    run(["cmake", "--build", BUILD, "--target", *gn_targets], env=env)
    folder = gn_dir()
    if folder is None:
        raise SystemExit("GN did not write args.gn")
    check_gn_args(folder)

    listed = output(["ninja", "-C", folder, "-t", "targets", "all"], env=env)
    objects = sorted({m.group(1) for m in map(SMOKE_PATTERN.match, listed.splitlines()) if m})
    log(f"{len(objects)} media objects to compile first")
    note(f"GN done; compiling {len(objects)} media objects first")
    if not objects:
        raise SystemExit("found no media objects; the pattern no longer fits the build")
    # In pieces: a command line on Windows holds about 32 000 characters.
    chunk, size = [], 0
    chunks = [chunk]
    for name in objects:
        if size + len(name) + 1 > 24000:
            chunk, size = [], 0
            chunks.append(chunk)
        chunk.append(name)
        size += len(name) + 1
    for index, names in enumerate(chunks, 1):
        log(f"smoke compile, part {index} of {len(chunks)}")
        code = run(["ninja", "-C", folder, "-j4", "-k", "30", *names], env=env, check=False)
        if code != 0:
            raise SystemExit("the patched media code does not compile; see FAILED: above")
    note("the patched media code compiles")


# --- build ------------------------------------------------------------------

def progress_line(line):
    return re.match(r"^\[\d+/\d+\] ", line) is not None


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def cmd_build(args):
    env = build_env()
    job_start = float(os.environ.get("IKE_JOB_START", time.time()))
    deadline = job_start + args.until_minute * 60
    left = deadline - time.time()
    log(f"building until minute {args.until_minute} of the job: {left / 60:.0f} minutes left")
    if left < 300:
        log("too little time left to build in this stage")
        set_output("done", "false")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / f"build-stage-{os.environ.get('IKE_STAGE', '0')}.log"
    process = subprocess.Popen(
        ["cmake", "--build", str(BUILD), "--parallel"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

    import threading
    failed_lines = []
    last = {"line": ""}

    def pump():
        with open(log_path, "w", encoding="utf-8", errors="replace") as handle:
            for line in process.stdout:
                handle.write(line)
                stripped = line.rstrip()
                last["line"] = stripped
                # Progress lines are kept in the file; the job log gets one in
                # two hundred of them and everything else.
                if progress_line(stripped):
                    pump.count += 1
                    if pump.count % 200 and time.time() - pump.noted <= 1900:
                        continue
                if stripped.startswith("FAILED:"):
                    failed_lines.append(stripped)
                    if len(failed_lines) <= 8:
                        print(f"::error title=Build::{stripped[:300]}", flush=True)
                print(stripped, flush=True)
                # A note on the job every half hour: the log of a running job
                # cannot be read from outside, its notes can.
                if progress_line(stripped) and time.time() - pump.noted > 1900:
                    pump.noted = time.time()
                    print(f"::notice title=Build progress, stage {os.environ.get('IKE_STAGE', '?')}::"
                          f"{stripped[:120]}", flush=True)
    pump.count = 0
    pump.noted = time.time() - 1500
    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    timed_out = False
    while True:
        try:
            process.wait(timeout=30)
            break
        except subprocess.TimeoutExpired:
            if time.time() >= deadline:
                timed_out = True
                log("time is up for this stage: stopping Ninja")
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    process.wait(timeout=120)
                except (subprocess.TimeoutExpired, OSError):
                    pass
                kill_tree(process.pid)
                break
    reader.join(timeout=30)
    # Nothing may still hold files of the build folder when it is packed.
    for name in ("ninja.exe", "cl.exe", "link.exe", "mspdbsrv.exe", "vctip.exe"):
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)

    progress = re.match(r"^\[(\d+)/(\d+)\]", last["line"] or "")
    if progress:
        log(f"last progress line: {progress.group(0)}")
        summary(f"- stage {os.environ.get('IKE_STAGE', '?')}: Ninja at `{progress.group(0)}`")
    if timed_out:
        set_output("done", "false")
        note(f"time is up, build not finished: {last['line'][:100]}")
        return
    if process.returncode != 0:
        set_output("done", "false")
        summary("**Build failed.**\n\n```\n" + "\n".join(failed_lines[:40]) + "\n```")
        raise SystemExit(f"the build failed with code {process.returncode}")
    set_output("done", "true")
    summary("- build finished")
    note("build finished")


# --- install, evidence, package ---------------------------------------------

def cmd_install(_args):
    env = build_env()
    if INSTALL.exists():
        shutil.rmtree(INSTALL)
    run(["cmake", "--install", BUILD, "--prefix", INSTALL], env=env)
    for path in sorted(INSTALL.rglob("*")):
        if path.is_file() and path.suffix.lower() in (".dll", ".exe", ".pak", ".dat", ".bin"):
            if "qtwebengine_locales" in path.parts:
                continue
            log(f"  {path.relative_to(INSTALL)}  {path.stat().st_size:,}")


def link_inputs(folder):
    """Every object file and library the linker gets for Qt6WebEngineCore.dll."""
    files = []
    for rsp in sorted(folder.glob("QtWebEngineCore_*.rsp")):
        if not re.search(r"_(objects|archives)\.rsp$", rsp.name):
            continue
        text = rsp.read_text(encoding="utf-8", errors="replace")
        for token in re.findall(r'"([^"]+)"|(\S+)', text):
            name = token[0] or token[1]
            if name.lower().endswith((".obj", ".o", ".lib", ".a")):
                path = Path(name)
                files.append(path if path.is_absolute() else folder / path)
    return files


def scan_files(files, needles):
    """How many of |files| contain each of |needles| (bytes)."""
    hits = {needle: [] for needle in needles}
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for needle in needles:
            if needle in data:
                hits[needle].append(str(path))
    return hits


def cmd_evidence(_args):
    """Writes down what went into the engine and fails if a decoder or encoder
    for H.264 / AAC is among it."""
    folder = gn_dir()
    if folder is None:
        raise SystemExit("no GN build folder")
    target = OUT / "evidence"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    problems = []
    report = [f"Qt WebEngine {VERSIONS['qtwebengine_tag']} "
              f"(Chromium {VERSIONS['chromium_version']}), I.K.E. Windows patches", ""]

    check_gn_args(folder)
    shutil.copy2(folder / "args.gn", target / "args.gn")

    config = SRC / "src/3rdparty/chromium/third_party/ffmpeg/chromium/config/Chromium/win/x64"
    for name in ("libavcodec/codec_list.c", "libavcodec/parser_list.c",
                 "libavformat/demuxer_list.c"):
        text = (config / name).read_text(encoding="utf-8")
        (target / name.replace("/", "_")).write_text(text, encoding="utf-8")
        entries = re.findall(r"&(ff_[a-z0-9_]+)", text)
        report.append(f"FFmpeg {name}: {' '.join(entries)}")
        for entry in entries:
            if entry in FORBIDDEN_SYMBOLS:
                problems.append(f"{name} lists {entry}")
    ffmpeg_ninja = folder / "obj/third_party/ffmpeg"
    used = "?"
    for ninja_file in ffmpeg_ninja.glob("*.ninja"):
        text = ninja_file.read_text(encoding="utf-8", errors="replace")
        found = set(re.findall(r"chromium/config/(Chrom[a-z]+)/win/x64", text))
        if found:
            used = ",".join(sorted(found))
            break
    report.append(f"FFmpeg configuration the build includes: {used}")
    if used not in ("Chromium", "?"):
        problems.append(f"FFmpeg is built with the configuration '{used}', not 'Chromium'")

    inputs = link_inputs(folder)
    report += ["", f"Link inputs of Qt6WebEngineCore.dll: {len(inputs)} object files and libraries"]
    if len(inputs) < 1000:
        problems.append(f"only {len(inputs)} link inputs found; the list was not understood")
    names = [str(p).replace("\\", "/").lower() for p in inputs]
    for fragment in ("openh264", "/h264dec", "h264_slice", "h264_cabac", "/aacdec", "aacsbr",
                     "aacps", "hevcdec"):
        matching = [n for n in names if fragment in n]
        report.append(f"  link inputs with '{fragment}' in the name: {len(matching)}")
        if matching:
            problems.append(f"link inputs named like a decoder: {matching[:5]}")
    needles = [s.encode() for s in FORBIDDEN_SYMBOLS + REPORTED_SYMBOLS + EXPECTED_SYMBOLS]
    hits = scan_files(inputs, needles)
    for symbol in FORBIDDEN_SYMBOLS:
        found = hits[symbol.encode()]
        report.append(f"  symbol {symbol}: in {len(found)} link inputs")
        if found:
            problems.append(f"{symbol} is in {found[:3]}")
    for symbol in REPORTED_SYMBOLS:
        report.append(f"  symbol {symbol} (reads headers, decodes nothing): "
                      f"in {len(hits[symbol.encode()])} link inputs")
    for symbol in EXPECTED_SYMBOLS:
        found = hits[symbol.encode()]
        report.append(f"  symbol {symbol} (free, expected): in {len(found)} link inputs")
        if not found:
            problems.append(f"{symbol} not found: the search does not see FFmpeg's symbols")

    maps = [p for p in (BUILD / "bin" / "Qt6WebEngineCore.map",
                        BUILD / "lib" / "Qt6WebEngineCore.map",
                        BUILD / "src" / "core" / "Qt6WebEngineCore.map",
                        BUILD / "Qt6WebEngineCore.map") if p.exists()]
    if not maps:
        maps = sorted(BUILD.rglob("Qt6WebEngineCore.map"))
    if maps:
        data = maps[0].read_bytes()
        report += ["", f"Linker map {maps[0].name}: {len(data):,} bytes"]
        for symbol in FORBIDDEN_SYMBOLS:
            count = data.count(symbol.encode())
            report.append(f"  {symbol}: {count} occurrences")
            if count:
                problems.append(f"the linker map names {symbol}")
        for symbol in EXPECTED_SYMBOLS:
            count = data.count(symbol.encode())
            report.append(f"  {symbol} (free, expected): {count} occurrences")
            if not count:
                problems.append(f"the linker map does not name {symbol}")
        with zipfile.ZipFile(target / "Qt6WebEngineCore.map.zip", "w",
                             zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(maps[0], maps[0].name)
    else:
        report += ["", "Linker map: not written (the link inputs above are the evidence)"]

    report += ["", "RESULT: " + ("FAILED" if problems else
                                 "no H.264 / AAC / H.265 decoder and no OpenH264 in the link")]
    report += [f"  problem: {p}" for p in problems]
    text = "\n".join(report) + "\n"
    (target / "codec-evidence.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    summary("### What is linked in\n\n```\n" + text + "```")
    if problems:
        raise SystemExit("a forbidden decoder or encoder is part of the build")


# The layout of the PyPI wheel PyQt6-WebEngine-Qt6: PyQt6/Qt6/{bin,resources,...}
PACKAGE_RULES = (
    ("bin", re.compile(r"^(Qt6WebEngine[A-Za-z]*\.dll|QtWebEngineProcess\.exe)$")),
    ("resources", re.compile(r"^(icudtl\.dat|qtwebengine_.*\.pak|v8_context_snapshot\.bin)$")),
    ("translations/qtwebengine_locales", re.compile(r"^.*\.pak$")),
    ("qml/QtWebEngine", re.compile(r"^.*$")),
    ("qml/QtWebEngine/ControlsDelegates", re.compile(r"^.*$")),
)


def cmd_package(_args):
    """Lays the built files out as in the PyPI wheel, to be copied over an
    installed PyQt6-WebEngine-Qt6, and lists their SHA-256."""
    version = VERSIONS["qtwebengine_tag"].lstrip("v")
    stage = OUT / "package"
    if stage.exists():
        shutil.rmtree(stage)
    base = stage / "PyQt6" / "Qt6"
    copied = []
    for folder, pattern in PACKAGE_RULES:
        source = INSTALL / folder
        if not source.is_dir():
            continue
        for path in sorted(source.iterdir()):
            if not path.is_file() or not pattern.match(path.name):
                continue
            if path.suffix.lower() in (".pdb", ".lib", ".map", ".exp"):
                continue
            if ".debug." in path.name or path.name.endswith("d.dll") and \
                    (source / (path.name[:-5] + ".dll")).exists():
                continue
            destination = base / folder / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied.append(destination)
    required = ("bin/Qt6WebEngineCore.dll", "bin/QtWebEngineProcess.exe",
                "resources/icudtl.dat", "resources/qtwebengine_resources.pak",
                "resources/v8_context_snapshot.bin",
                "translations/qtwebengine_locales/en-US.pak")
    for name in required:
        if not (base / name).exists():
            raise SystemExit(f"the build did not produce {name}")

    core = base / "bin" / "Qt6WebEngineCore.dll"
    data = core.read_bytes()
    problems = []
    lines = [f"Qt6WebEngineCore.dll: {len(data):,} bytes"]
    for needle in FORBIDDEN_STRINGS:
        count = data.count(needle)
        lines.append(f"  text {needle.decode()!r} (only in a decoder / encoder): {count}")
        if count:
            problems.append(needle.decode())
    for needle in EXPECTED_STRINGS:
        count = data.count(needle)
        lines.append(f"  text {needle.decode()!r} (expected): {count}")
        if not count:
            problems.append("missing " + needle.decode())
    text = "\n".join(lines) + "\n"
    (OUT / "evidence").mkdir(parents=True, exist_ok=True)
    (OUT / "evidence" / "binary-strings.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    summary("### Text in Qt6WebEngineCore.dll\n\n```\n" + text + "```")
    if problems:
        raise SystemExit(f"Qt6WebEngineCore.dll fails the text check: {problems}")

    notes = stage / "IKE-ENGINE.txt"
    notes.write_text(
        f"Qt WebEngine {version} (Chromium {VERSIONS['chromium_version']}) built by I.K.E.\n"
        f"with the patches in packaging/windows/qtwebengine/patches of the I.K.E. repository,\n"
        f"against Qt {VERSIONS['qt_version']} ({VERSIONS['qt_arch']}).\n"
        "H.264 and AAC are decoded by Windows (Media Foundation); this engine contains no\n"
        "decoder for them. Copy the PyQt6 folder over the one of an installed\n"
        f"PyQt6-WebEngine-Qt6 {VERSIONS['pyqt']['PyQt6-WebEngine-Qt6']}.\n"
        f"Source commit of this build: {os.environ.get('GITHUB_SHA', 'unknown')}\n",
        encoding="utf-8")

    sums = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        sums.append(f"{sha256_file(path)}  {path.relative_to(stage).as_posix()}")
    (stage / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    archive = OUT / f"ike-qtwebengine-{version}-win64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            bundle.write(path, path.relative_to(stage).as_posix())
    (OUT / "SHA256SUMS.txt").write_text(
        f"{sha256_file(archive)}  {archive.name}\n\n# files inside\n" + "\n".join(sums) + "\n",
        encoding="utf-8")
    log(f"{len(copied)} files, {archive.name} {archive.stat().st_size / 2**20:.0f} MB")
    print((OUT / "SHA256SUMS.txt").read_text(encoding="utf-8")[:1500], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("prepare", cmd_prepare), ("patch", cmd_patch),
                           ("configure", cmd_configure), ("smoke", cmd_smoke),
                           ("pack", cmd_pack), ("install", cmd_install),
                           ("evidence", cmd_evidence), ("package", cmd_package)):
        commands.add_parser(name).set_defaults(function=function)
    restore = commands.add_parser("restore")
    restore.add_argument("--source", default="none",
                         help="first stage only: auto, none, or the id of an earlier run")
    restore.set_defaults(function=cmd_restore)
    build = commands.add_parser("build")
    build.add_argument("--until-minute", type=int, default=290,
                       help="stop building this many minutes after the job started")
    build.set_defaults(function=cmd_build)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("this script builds on Windows only")
    args.function(args)


if __name__ == "__main__":
    main()
