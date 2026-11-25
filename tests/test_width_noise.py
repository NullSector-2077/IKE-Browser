"""The text width noise of Strict and Maximum (fingerprint.js widthNoise):
never the real width, always within 3 in a million, 0 stays 0. Run in Node on
the function's own source, so every seed and width can be tried quickly (a run
in the engine draws one site key per session and once missed the 1 width in 61
that kept its real value)."""

import json
import re
import shutil
import subprocess

import pytest
from conftest import APP

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="Node is not installed here")


def source():
    text = (APP / "ike/resources/fingerprint.js").read_text("utf-8")
    m = re.search(r"\n  function widthNoise\(real, seed, F, U\) \{\n.*?\n  \}\n", text, re.S)
    assert m, "widthNoise not found in fingerprint.js"
    return m.group(0)


@needs_node
def test_the_width_noise_never_keeps_the_real_width():
    script = source() + r"""
var F = new Float64Array(1), U = new Uint32Array(F.buffer), out = {same: 0, far: 0, zero: 0, n: 0};
var s = 12345;
function rnd() { s = (s * 1103515245 + 12345) >>> 0; return s; }
for (var i = 0; i < 200000; i++) {
  var seed = rnd() | 0, real = (rnd() % 200000) / 64 + 0.015625;
  var got = widthNoise(real, seed, F, U);
  out.n++;
  if (got === real) out.same++;
  if (Math.abs(got / real - 1) > 3.0000001e-6) out.far++;
}
out.zero = widthNoise(0, 7, F, U);
console.log(JSON.stringify(out));
"""
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["n"] == 200000 and out["same"] == 0 and out["far"] == 0 and out["zero"] == 0, out
