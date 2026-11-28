"""Absolute invariants of the fingerprinting protection, context by context (the worker guard study,
docs/review/worker-guard-study.md: "Nothing gets worse" compares main with a candidate on the same
engine, so a protection that an engine update breaks on both sides passes it; this test states what
each level must give in every place a site can read values, whatever the engine).

The probe of tests/fp_audit.py (cores, memory, languages, time zone, user agent and client hints,
an OffscreenCanvas picture and a text width, WebGL, WebGPU, a font by local()) is read in the page,
a frame of the same site, a srcdoc frame, an empty frame the page fills, blob, data:, file and nested
workers, shared workers from a blob and from a file, and a service worker.

- Balanced, Kontrol, Maximum: every place the protection reaches gives the page's own values (the
  data: worker has a seed of its own, by design, and is left out of the comparison).
- Balanced: a site's own file workers, shared and service workers keep the engine's values (the
  owner's decisions), they are not compared.
- Kontrol: the site's own shared and service workers run with the engine's values (said to the
  user); a dedicated worker from the site's file is protected (its protected copy).
- Maximum: the site's own shared and service workers do not start (the owner's decision of
  2026-11-28); every worker that starts gives the page's values.
- The page's canvas differs from the engine's own (Off): the noise is really there.
- A negative test: with the protection's worker prelude emptied, this very comparison fails, so the
  test can see a protection that no longer reaches the workers.
"""

import json

import fp_audit
import pytest
from fp_audit import measure, site  # noqa: F401  (the fixture)

KEYS = ("cores", "mem", "langs", "lang", "tz", "locale", "ua", "platform", "brands", "he", "canvas", "measure",
        "glVendor", "glRenderer", "glExts", "glMax", "glPixels", "webgpu", "fontLocal")


def differ(page, other):
    return {k: [page.get(k), other.get(k)] for k in KEYS if page.get(k) != other.get(k)}


@pytest.mark.parametrize("level", ["balanced", "strict", "maximum"])
def test_every_protected_place_gives_the_pages_values(run_ike, site, level):  # noqa: F811
    got = measure(run_ike, site, level)
    page = got["page"]
    protected = ["frame", "srcdoc", "emptyFrame", "blobWorker", "nestedWorker", "sharedBlob"]
    if level in ("strict", "maximum"):
        protected.append("fileWorker")
    bad = {}
    for ctx in protected:
        v = got.get(ctx)
        if not isinstance(v, dict):
            bad[ctx] = v
            continue
        d = differ(page, v)
        if d:
            bad[ctx] = d
    assert not bad, (level, json.dumps(bad)[:3000])
    if level == "strict":
        # the site's own shared and service workers run, with the engine's values (said to the user)
        assert isinstance(got["sharedFile"], dict) and isinstance(got["serviceWorker"], dict), got
    if level == "maximum":
        assert not isinstance(got["sharedFile"], dict), got["sharedFile"]
        assert not isinstance(got["serviceWorker"], dict), got["serviceWorker"]


def test_the_noise_is_there(run_ike, site):  # noqa: F811
    off = measure(run_ike, site, "off")["page"]
    for level in ("balanced", "maximum"):
        page = measure(run_ike, site, level)["page"]
        assert page["canvas"] != off["canvas"], (level, page["canvas"])


def test_a_lost_worker_protection_is_seen(run_ike, site):  # noqa: F811
    """The negative test: the protection's worker prelude emptied in memory (as an update that
    broke it would leave it); the comparison above must see the blob worker give other values."""
    from test_trusted_types_workers import STEPS
    broken = "    ike.shields._fp_src = ike.shields._fp_src.replace(\n" \
             "        \"function preludeFor(address, ownSeed, run, hello) {\",\n" \
             "        \"function preludeFor(address, ownSeed, run, hello) { return ''; \", 1)\n" \
             "    ike.shields.apply_settings()\n"
    script = "PAGES = %r\n" % [("audit", "http://localhost:%d/p.html" % site)] + STEPS.replace(
        "def steps(ike, qapp, out):\n", "def steps(ike, qapp, out):\n" + broken, 1)
    out = run_ike(script, settings={"shield_level": "balanced"},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": fp_audit.GL_FLAGS}, timeout=300, internal_errors=True)
    got = json.loads(out["audit"])
    assert isinstance(got["blobWorker"], dict), got["blobWorker"]
    assert differ(got["page"], got["blobWorker"]), "an emptied prelude went unnoticed"
