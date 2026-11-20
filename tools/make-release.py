#!/usr/bin/env python3
"""Prepare the signed self-update files of an I.K.E. release.

Run it on the owner's computer, from a clone of the repository at the commit
being released. It writes into dist/release-<version>/:

    ike-<version>.tar.gz              the ike/ folder (the self-update payload)
    stable.json, stable.json.sig      the manifest and its Ed25519 signature
    beta.json, beta.json.sig          the same for the beta channel

and checks every signature against the public key in data/update.json before
it finishes. Upload these files, together with the Arch package, as the
assets of a new GitHub release (see docs/UPDATES.md).

    python3 tools/make-release.py [--key ~/.ike-signing/ike-update.key]
                                  [--channels stable,beta]

The private key is read from its file and the passphrase is asked on the
terminal; neither is stored anywhere. Only the `cryptography` module is needed.
"""

import argparse
import base64
import getpass
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY = Path.home() / ".ike-signing" / "ike-update.key"


def read_var(name):
    text = (ROOT / "ike" / "__init__.py").read_text("utf-8")
    return re.search(r'^%s\s*=\s*"([^"]+)"' % name, text, re.M).group(1)


ENGINE_FILES = ("__init__.py", "adblock.pyi", "py.typed", "ike_adblock.abi3.so")


def licence_files(engine=None):
    """[(file, name)] of the licences that travel with the update (1.1.18):
    those the package just built installs in /usr/share/licenses/ike-browser
    (next to the engine folder of pkg/), else the repository's own."""
    if engine is not None:
        parents = Path(engine).resolve().parents
        if len(parents) > 3:
            installed = parents[3] / "share" / "licenses" / "ike-browser"
            if installed.is_dir():
                return sorted((p, p.name) for p in installed.iterdir() if p.is_file())
    files = [ROOT / "LICENSE", ROOT / "COPYRIGHT", ROOT / "docs" / "THIRD-PARTY.md"]
    files += sorted(p for p in (ROOT / "licenses").iterdir() if p.is_file())
    missing = [p.name for p in files if not p.is_file()]
    if missing:
        raise SystemExit("licence files missing: %s" % ", ".join(missing))
    return sorted((p, p.name) for p in files)


def build_payload(engine=None):
    """A reproducible .tar.gz of ike/ (no caches, fixed owners and dates).
    engine: the folder of the AdBlock engine module just built for this release
    (vendor/adblock of the package); it travels as ike/_engine/adblock/, so a
    new engine reaches every user with the self-update (1.1.12). The licences
    and notices of everything shipped travel as ike/_licenses/ (1.1.18)."""
    files = sorted((p, p.relative_to(ROOT).as_posix()) for p in (ROOT / "ike").rglob("*")
                   if "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".pyo"))
                   and "_engine" not in p.relative_to(ROOT / "ike").parts
                   and "_licenses" not in p.relative_to(ROOT / "ike").parts)
    licences = licence_files(engine)
    files.append((licences[0][0].parent, "ike/_licenses"))
    files += [(p, "ike/_licenses/" + name) for p, name in licences]
    if engine is not None:
        engine = Path(engine)
        missing = [n for n in ENGINE_FILES if not (engine / n).is_file()]
        if missing:
            raise SystemExit("the engine folder %s lacks %s" % (engine, ", ".join(missing)))
        files.append((engine, "ike/_engine"))          # its folders first
        files.append((engine, "ike/_engine/adblock"))
        files += [(engine / n, "ike/_engine/adblock/" + n) for n in ENGINE_FILES]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for p, arcname in files:
            info = tar.gettarinfo(str(p), arcname=arcname)
            if not (info.isfile() or info.isdir()):
                raise SystemExit("not a regular file: %s" % p)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if info.isdir() else 0o644
            if info.isfile():
                with open(p, "rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def load_key(path, passphrase=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    data = path.read_bytes()
    if passphrase is None and b"ENCRYPTED" in data:
        passphrase = getpass.getpass("Passphrase for %s: " % path)
    key = load_pem_private_key(data, password=passphrase.encode() if passphrase else None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("%s is not an Ed25519 key" % path)
    return key


def public_b64(key):
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def verify(pub_b64, data, sig_b64):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(base64.b64decode(sig_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def inside_repo(path):
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


# how long a signed manifest is valid (1.1.18, security audit F5): a copy
# served after that (an old one kept back to hide a newer release) installs
# nothing, and the next release's manifest is valid again
VALID_DAYS = 180
# a new release reaches every installation over this many hours (each one has
# its own fixed place, 0-99); "--rollout-hours 0" sends it to all at once
ROLLOUT_HOURS = 24


def make(key_path, out_dir, channels, passphrase=None, update_file=None, engine=None,
         rollout_hours=ROLLOUT_HOURS, halt=False, now=None):
    key_path = Path(key_path).expanduser()
    if inside_repo(key_path):
        raise SystemExit("refusing to use a private key stored inside the repository: move it out")
    update = json.loads(Path(update_file or ROOT / "data" / "update.json").read_text("utf-8"))
    if not update.get("pubkey") or not update.get("url"):
        raise SystemExit("data/update.json has no url or public key")
    key = load_key(key_path, passphrase)
    if public_b64(key) != update["pubkey"]:
        raise SystemExit("this private key does not match the public key in data/update.json")

    version = read_var("__version__")
    payload = build_payload(engine)
    issued = int(now if now is not None else time.time())
    manifest = {"version": version, "payload": "ike-%s.tar.gz" % version,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "min_system": read_var("__min_system__"),
                "issued": issued, "expires": issued + VALID_DAYS * 86400,
                "rollout": {"start": issued, "hours": max(0, int(rollout_hours))}}
    if halt:
        # stops a release that went wrong: re-signed manifest of the same
        # version, uploaded over the release's own (docs/UPDATES.md)
        manifest["halt"] = True

    out = Path(out_dir or ROOT / "dist" / ("release-" + version))
    out.mkdir(parents=True, exist_ok=True)
    (out / manifest["payload"]).write_bytes(payload)
    raw = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    for ch in channels:
        sig = base64.b64encode(key.sign(raw)).decode()
        if not verify(update["pubkey"], raw, sig):
            raise SystemExit("signature check failed")
        (out / (ch + ".json")).write_bytes(raw)
        (out / (ch + ".json.sig")).write_text(sig + "\n", "ascii")
    return out, manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--key", default=str(DEFAULT_KEY), help="Ed25519 private key (PEM)")
    ap.add_argument("--out", help="output folder (default dist/release-<version>)")
    ap.add_argument("--channels", default="stable,beta")
    ap.add_argument("--engine", help="folder of the AdBlock engine module built for this release "
                    "(pkg/ike-browser/usr/lib/ike-browser/vendor/adblock after makepkg)")
    ap.add_argument("--rollout-hours", type=int, default=ROLLOUT_HOURS,
                    help="hours over which the release reaches every installation (0: all at once)")
    ap.add_argument("--halt", action="store_true",
                    help="sign a manifest that stops this version from being installed")
    a = ap.parse_args(argv)
    channels = [c for c in a.channels.split(",") if c]
    out, manifest = make(a.key, a.out, channels, engine=a.engine, rollout_hours=a.rollout_hours,
                         halt=a.halt)
    print("I.K.E. %s: signed update files in %s" % (manifest["version"], out))
    for p in sorted(out.iterdir()):
        print("  " + p.name)
    print("\nPublish them (not as a draft or pre-release) with:\n"
          "  gh release create v{v} {o}/* <package> --title 'I.K.E. {v}' "
          "--notes-file <notes>".format(v=manifest["version"], o=out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
