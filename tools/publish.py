#!/usr/bin/env python3
"""Sign and publish an I.K.E. release with one command, on the owner's computer.

From a clone of the repository (the owner's is ~/IKE-Browser):

    python3 tools/publish.py              sign and publish what main holds
    python3 tools/publish.py --dry-run    everything except the GitHub release

It stops, changing nothing on GitHub, at the first thing that is not right:

1. `git`, `gh` (signed in) and `makepkg` are there; the clone is on `main`,
   without local changes, brought up to date and equal to GitHub's `main`;
2. the version in ike/__init__.py and the PKGBUILD agree, and that version is
   not published yet;
3. the automatic tests ("tests") passed on exactly that commit on GitHub;
4. the package is built (`makepkg -Csf`);
5. the update files are signed by tools/make-release.py, which asks the
   passphrase of the private key (the key never leaves this computer); the
   AdBlock engine just built travels inside the update, so every user gets
   every release by the self-update, without a new package;
6. the release notes are taken from the version's section of CHANGELOG.md;
7. the release is created on GitHub, its tag on that exact commit;
8. the published files are read back from GitHub: the signature, the version
   and the hash of the update must match.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "NullSector-2077/IKE-Browser"
CHECK_NAME = "tests"


class Stop(Exception):
    """A reason not to go on, shown to the owner."""


def run(cmd, capture=True, check=True, cwd=ROOT):
    out = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, check=False)
    if check and out.returncode:
        detail = (out.stderr or out.stdout or "").strip() if capture else ""
        raise Stop("%s non è riuscito%s" % (" ".join(cmd[:3]), (":\n" + detail[-800:]) if detail else ""))
    return out.stdout.strip() if capture else ""


def say(text):
    print("\033[1;36m==>\033[0m " + text, flush=True)


def load_make_release():
    spec = importlib.util.spec_from_file_location("make_release", ROOT / "tools" / "make-release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- checks that need no network (tested in tests/test_publish.py) -------------

def versions(root):
    """(version, pkgver, pkgrel) from ike/__init__.py and the PKGBUILD."""
    init = (root / "ike" / "__init__.py").read_text("utf-8")
    pkgbuild = (root / "PKGBUILD").read_text("utf-8")
    version = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    pkgver = re.search(r"^pkgver=(\S+)", pkgbuild, re.M)
    pkgrel = re.search(r"^pkgrel=(\S+)", pkgbuild, re.M)
    if not (version and pkgver and pkgrel):
        raise Stop("versione non trovata in ike/__init__.py o nel PKGBUILD")
    return version.group(1), pkgver.group(1), pkgrel.group(1)


def package_name(version, pkgrel):
    return "ike-browser-%s-%s-x86_64.pkg.tar.zst" % (version, pkgrel)


def release_notes(changelog_text, version):
    """The CHANGELOG section of a version, without its heading."""
    m = re.search(r"^## %s[ \t]*\n(.*?)(?=^## |\Z)" % re.escape(version), changelog_text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise Stop("CHANGELOG.md non ha una sezione '## %s'" % version)
    return m.group(1).strip() + "\n"


def check_runs_path(sha, name):
    """The API path of the checks of a commit that have this name (all of them, whatever else ran)."""
    from urllib.parse import quote
    return "repos/%s/commits/%s/check-runs?check_name=%s&filter=all&per_page=100" % (REPO, sha, quote(name))


def tests_passed(check_runs, name=CHECK_NAME):
    """'ok', 'running' or 'failed' for the check `name` of a commit."""
    runs = [r for r in check_runs if r.get("name") == name]
    if not runs:
        return "missing"
    if any(r.get("conclusion") == "success" for r in runs):
        return "ok"
    if any(r.get("status") != "completed" for r in runs):
        return "running"
    return "failed"


def check_published(manifest_raw, signature, payload, version, pubkey, verify):
    """The files read back from GitHub are the ones just signed."""
    if not verify(pubkey, manifest_raw, signature.strip()):
        raise Stop("la firma di stable.json pubblicato non è valida")
    manifest = json.loads(manifest_raw)
    if manifest.get("version") != version:
        raise Stop("GitHub offre la versione %s invece di %s" % (manifest.get("version"), version))
    if hashlib.sha256(payload).hexdigest() != manifest.get("sha256"):
        raise Stop("l'hash dell'aggiornamento pubblicato non corrisponde")


# --- the steps ------------------------------------------------------------------

def fetch(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(5)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="tutto tranne la release su GitHub")
    ap.add_argument("--key", help="chiave privata (predefinita: ~/.ike-signing/ike-update.key)")
    ap.add_argument("--urgente", action="store_true",
                    help="a tutti subito (correzione di sicurezza), invece che nell'arco di 24 ore")
    a = ap.parse_args(argv)
    try:
        return publish(a)
    except Stop as e:
        print("\n\033[1;31mFermato:\033[0m %s\nSu GitHub non è cambiato niente." % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrotto. Su GitHub non è cambiato niente.", file=sys.stderr)
        return 1


def publish(a):
    for tool in ("git", "gh", "makepkg"):
        if not shutil.which(tool):
            raise Stop("manca il programma '%s'" % tool)
    run(["gh", "auth", "status"])

    say("Controllo la copia del repository")
    if run(["git", "branch", "--show-current"]) != "main":
        raise Stop("non sei su main: esegui 'git switch main'")
    if run(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise Stop("ci sono modifiche locali nei file del repository: 'git status' le mostra")
    run(["git", "pull", "--ff-only", "-q", "origin", "main"])
    sha = run(["git", "rev-parse", "HEAD"])
    if sha != run(["git", "rev-parse", "origin/main"]):
        raise Stop("la tua main è diversa da quella di GitHub")

    version, pkgver, pkgrel = versions(ROOT)
    if version != pkgver:
        raise Stop("ike/__init__.py dice %s ma il PKGBUILD dice %s" % (version, pkgver))
    tag = "v" + version
    if subprocess.run(["gh", "release", "view", tag, "--repo", REPO], cwd=ROOT,
                      capture_output=True).returncode == 0:
        raise Stop("la versione %s è già pubblicata: prima serve una PR che alzi la versione" % version)
    say("Versione %s, pacchetto %s, commit %s" % (version, pkgrel, sha[:10]))

    say("Controllo che i test di GitHub siano passati su questo commit")
    # the tests, and the security tests with the sandbox on (review 2 of 1.1.19, H3); each asked by
    # its name: a commit of main carries more than 100 checks (the automation's own runs), and the
    # first page of all of them may not hold "tests" at all (1.1.23: "not started" although it passed)
    for name, what in ((CHECK_NAME, "i test"), ("sandbox", "i test di sicurezza (sandbox)")):
        checks = json.loads(run(["gh", "api", check_runs_path(sha, name)]))
        state = tests_passed(checks.get("check_runs", []), name)
        if state != "ok":
            raise Stop({"missing": "%s non sono ancora partiti su questo commit" % what,
                        "running": "%s sono ancora in corso: riprova quando finiscono" % what,
                        "failed": "%s sono falliti su questo commit" % what}[state])

    notes = release_notes((ROOT / "CHANGELOG.md").read_text("utf-8"), version)

    say("Costruisco il pacchetto (makepkg -Csf)")
    run(["makepkg", "-Csf"], capture=False)
    pkg = ROOT / package_name(version, pkgrel)
    if not pkg.is_file():
        raise Stop("makepkg non ha prodotto %s" % pkg.name)

    # the engine just built goes inside the signed update: every user gets it
    # by the self-update, without a new package (1.1.12)
    engine = ROOT / "pkg" / "ike-browser" / "usr" / "lib" / "ike-browser" / "vendor" / "adblock"
    if not (engine / "ike_adblock.abi3.so").is_file():
        raise Stop("makepkg non ha lasciato il motore dell'ad blocker in %s" % engine)

    say("Firmo gli aggiornamenti: ti chiedo la passphrase della chiave")
    cmd = [sys.executable, str(ROOT / "tools" / "make-release.py"), "--engine", str(engine)]
    if a.key:
        cmd += ["--key", a.key]
    if getattr(a, "urgente", False):
        cmd += ["--rollout-hours", "0"]
    # its own advice on publishing by hand is not shown: this command does it;
    # the passphrase is asked on the terminal (stderr), so it still shows
    signed = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, text=True, check=False)
    if signed.returncode:
        raise Stop("la firma non è riuscita: passphrase sbagliata, o la chiave non è quella di I.K.E.")
    out = ROOT / "dist" / ("release-" + version)
    assets = sorted(p for p in out.iterdir() if p.is_file())
    if not any(p.name == "stable.json.sig" for p in assets):
        raise Stop("make-release.py non ha scritto i file firmati in %s" % out)
    notes_file = out.parent / ("notes-%s.md" % version)
    notes_file.write_text(notes, "utf-8")

    if a.dry_run:
        say("Prova finita (--dry-run): tutto pronto, NIENTE pubblicato. Verrebbero pubblicati:")
        for p in assets + [pkg]:
            print("    " + p.name)
        return 0

    say("Pubblico la release %s su GitHub" % tag)
    run(["gh", "release", "create", tag, *map(str, assets), str(pkg), "--repo", REPO,
         "--target", sha, "--title", "I.K.E. %s" % version, "--notes-file", str(notes_file)],
        capture=False)

    say("Verifico quello che GitHub offre agli utenti")
    mr = load_make_release()
    pubkey = json.loads((ROOT / "data" / "update.json").read_text("utf-8"))["pubkey"]
    base = "https://github.com/%s/releases/latest/download/" % REPO
    for i in range(6):
        manifest_raw = fetch(base + "stable.json")
        if json.loads(manifest_raw).get("version") == version or i == 5:
            break
        time.sleep(10)
    signature = fetch(base + "stable.json.sig").decode("ascii")
    payload = fetch(base + json.loads(manifest_raw)["payload"])
    check_published(manifest_raw, signature, payload, version, pubkey, mr.verify)

    say("Fatto: I.K.E. %s è pubblicata e verificata." % version)
    print("    Per installare il pacchetto su questo PC:\n    sudo pacman -U '%s'" % pkg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
