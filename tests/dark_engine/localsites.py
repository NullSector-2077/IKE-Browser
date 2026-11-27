"""Pages built here with the real themes and libraries many sites use, for what
the reachable real sites do not cover (CSS-in-JS, shadow DOM, CSS variables,
a style sheet from a CDN, a long form). Same layout as snapshot.py's output.

    python3 tests/dark_engine/localsites.py OUT_DIR VENV_BIN NODE_DIR

VENV_BIN: a virtualenv's bin with sphinx, python-docs-theme, furo, mkdocs-material.
NODE_DIR: a folder with node_modules holding react, react-dom, @mui/material,
@emotion/react, @emotion/styled, esbuild, lit, bootstrap.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

RST = """JSON encoder and decoder
========================

:mod:`json` exposes an API familiar to users of the standard library modules.
It encodes and decodes `JSON <https://json.org>`_, a lightweight data interchange format.

.. note::
   The JSON format is specified by RFC 7159 and by ECMA-404.

.. warning::
   Be cautious when parsing JSON data from untrusted sources.

Basic usage
-----------

.. function:: dumps(obj, *, indent=None, sort_keys=False)

   Serialize *obj* to a JSON formatted :class:`str`.

.. code-block:: python

   import json
   print(json.dumps({"4": 5, "6": 7}, sort_keys=True, indent=4))
   data = json.loads('["foo", {"bar": ["baz", null, 1.0, 2]}]')

=================  ======================
JSON               Python
=================  ======================
object             dict
array              list
string             str
number (int)       int
true / false       True / False
null               None
=================  ======================

Command line interface
----------------------

The ``json.tool`` module provides a simple command line interface to validate and pretty-print JSON objects.
If the optional ``infile`` and ``outfile`` arguments are not specified, standard input and output are used.

.. seealso::
   :pep:`8` and the Python tutorial.
"""

MD = """# JSON encoder and decoder

The `json` module exposes an API familiar to users of the standard library. It encodes and decodes
[JSON](https://json.org), a lightweight data interchange format.

!!! note
    The JSON format is specified by RFC 7159 and by ECMA-404.

!!! warning
    Be cautious when parsing JSON data from untrusted sources.

## Basic usage

```python
import json
print(json.dumps({"4": 5, "6": 7}, sort_keys=True, indent=4))
```

| JSON | Python |
|------|--------|
| object | dict |
| array | list |
| string | str |
| null | None |

=== "Linux"
    Run `python3 -m json.tool data.json`.
=== "Windows"
    Run `py -m json.tool data.json`.
"""

MUI = r"""
import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { AppBar, Toolbar, Typography, Button, Card, CardContent, CardActions, TextField, Chip, Alert,
  Table, TableHead, TableRow, TableCell, TableBody, Tabs, Tab, Container, Grid, Paper, Switch,
  FormControlLabel, Checkbox, CssBaseline } from '@mui/material';

function App() {
  const [tab, setTab] = React.useState(0);
  const [rows, setRows] = React.useState([['Keyboard', 49], ['Mouse', 19], ['Monitor', 189]]);
  React.useEffect(() => { const t = setTimeout(() => setRows(r => r.concat([['Headset', 59], ['Webcam', 39]])), 400);
    return () => clearTimeout(t); }, []);
  return (<>
    <CssBaseline />
    <AppBar position="static"><Toolbar><Typography variant="h6" sx={{ flexGrow: 1 }}>Shop dashboard</Typography>
      <Button color="inherit">Login</Button></Toolbar></AppBar>
    <Tabs value={tab} onChange={(e, v) => setTab(v)}><Tab label="Orders" /><Tab label="Stock" /><Tab label="Reports" /></Tabs>
    <Container sx={{ mt: 2 }}>
      <Alert severity="info">Three orders are waiting to be shipped.</Alert>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        <Grid item xs={6}><Card><CardContent><Typography variant="h5">Revenue</Typography>
          <Typography color="text.secondary">1 204 euro this week</Typography>
          <Chip label="+12%" color="success" size="small" /> <Chip label="new" variant="outlined" /></CardContent>
          <CardActions><Button size="small" variant="contained">Details</Button><Button size="small">Share</Button></CardActions></Card></Grid>
        <Grid item xs={6}><Paper sx={{ p: 2 }}><TextField label="Search orders" fullWidth size="small" />
          <FormControlLabel control={<Switch defaultChecked />} label="Only open" />
          <FormControlLabel control={<Checkbox />} label="Include drafts" /></Paper></Grid>
      </Grid>
      <Table size="small" sx={{ mt: 2 }}><TableHead><TableRow><TableCell>Item</TableCell><TableCell>Price</TableCell></TableRow></TableHead>
        <TableBody>{rows.map(r => <TableRow key={r[0]}><TableCell>{r[0]}</TableCell><TableCell>{r[1]} euro</TableCell></TableRow>)}</TableBody></Table>
    </Container></>);
}
createRoot(document.getElementById('root')).render(<App />);
"""

LIT = r"""
import { LitElement, html, css } from 'lit';
class InfoCard extends LitElement {
  static properties = { title: {} };
  static styles = css`:host{display:block;background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:16px;margin:12px 0;
    box-shadow:0 1px 3px rgba(0,0,0,.12)} h3{margin:0 0 8px;color:#24292f} p{color:#57606a;margin:0}
    .tag{display:inline-block;background:#ddf4ff;color:#0969da;border-radius:12px;padding:2px 8px;font-size:12px}`;
  render() { return html`<h3>${this.title}</h3><p><slot></slot></p><span class="tag">component</span>`; }
}
customElements.define('info-card', InfoCard);
class ActionBar extends LitElement {
  static styles = css`div{display:flex;gap:8px;background:var(--bar-bg,#f6f8fa);padding:8px;border-radius:6px}
    button{background:#2da44e;color:#fff;border:0;border-radius:6px;padding:6px 12px}
    button.alt{background:#f6f8fa;color:#24292f;border:1px solid #d0d7de}`;
  render() { return html`<div><button>Save</button><button class="alt">Cancel</button><button class="alt">Help</button></div>`; }
}
customElements.define('action-bar', ActionBar);
setTimeout(() => { const c = document.createElement('info-card'); c.title = 'Added later';
  c.textContent = 'This card was created by a script after the page loaded.'; document.body.appendChild(c); }, 400);
"""

LIT_HTML = """<!doctype html><meta charset=utf-8><title>Components</title>
<style>:root{--page-bg:#ffffff;--ink:#1f2328;--muted:#656d76;--bar-bg:#eef1f4}
body{font:15px/1.5 system-ui,sans-serif;margin:24px;background:var(--page-bg);color:var(--ink)}
.lead{color:var(--muted)}</style>
<h1>Web components</h1><p class=lead>Cards below draw their own styles inside a shadow root.</p>
<action-bar></action-bar>
<info-card title="Shadow DOM">Its style sheet lives inside the component and is not visible to the page.</info-card>
<info-card title="CSS variables">The bar takes its colour from a variable set by the page.</info-card>
<script src="app.js"></script>"""

FORM_HTML = """<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Checkout</title><link rel=stylesheet href="http://127.0.0.1:__TP__/snap/bootstrap-form/cdn.local/bootstrap.min.css">
<body class="bg-body-tertiary"><div class="container py-4" style="max-width:900px">
<h2>Checkout form</h2><p class="lead">Every required field is marked; the form checks itself when sent.</p>
<div class="row g-4"><div class="col-md-5 order-md-last"><h4 class="d-flex justify-content-between"><span class="text-primary">Your cart</span>
<span class="badge bg-primary rounded-pill">3</span></h4><ul class="list-group mb-3">
<li class="list-group-item d-flex justify-content-between"><div><h6 class="my-0">Product name</h6><small class="text-body-secondary">Brief description</small></div><span class="text-body-secondary">$12</span></li>
<li class="list-group-item d-flex justify-content-between bg-body-tertiary"><div class="text-success"><h6 class="my-0">Promo code</h6><small>EXAMPLECODE</small></div><span class="text-success">-$5</span></li>
<li class="list-group-item d-flex justify-content-between"><span>Total (USD)</span><strong>$20</strong></li></ul>
<div class="alert alert-warning">Shipping takes 3 days.</div></div>
<div class="col-md-7"><h4 class="mb-3">Billing address</h4><form class="needs-validation"><div class="row g-3">
<div class="col-sm-6"><label class="form-label">First name</label><input class="form-control" placeholder="First name"></div>
<div class="col-sm-6"><label class="form-label">Last name</label><input class="form-control" value="Rossi"></div>
<div class="col-12"><label class="form-label">Email <span class="text-body-secondary">(Optional)</span></label><input type=email class="form-control" placeholder="you@example.com"></div>
<div class="col-md-5"><label class="form-label">Country</label><select class="form-select"><option>Choose...</option><option>Italy</option></select></div>
<div class="col-md-4"><label class="form-label">State</label><select class="form-select"><option>Choose...</option></select></div>
<div class="col-md-3"><label class="form-label">Zip</label><input class="form-control is-invalid" value="x"><div class="invalid-feedback">Zip code required.</div></div>
</div><hr class="my-4"><div class="form-check"><input type=checkbox class="form-check-input" id=same checked><label class="form-check-label" for=same>Shipping address is the same</label></div>
<div class="form-check form-switch"><input class="form-check-input" type=checkbox checked><label class="form-check-label">Save this information</label></div>
<hr class="my-4"><button class="w-100 btn btn-primary btn-lg" type=button>Continue to checkout</button>
<div class="btn-group mt-3"><button class="btn btn-outline-secondary" type=button>Back</button><button class="btn btn-light" type=button>Help</button><button class="btn btn-danger" type=button>Cancel</button></div>
</form></div></div></div>"""


def manifest(d, url, entry):
    (d / "manifest.json").write_text(json.dumps({"url": url, "entry": entry, "site": "local.test"}))


def copy_tree(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def sphinx(out, venv, name, theme):
    work = out / ("_src_" + name)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    (work / "conf.py").write_text("project='Demo'\nhtml_theme=%r\nextensions=[]\n" % theme)
    (work / "index.rst").write_text(RST)
    subprocess.run([str(venv / "sphinx-build"), "-q", "-b", "html", str(work), str(work / "_build")], check=True)
    d = out / name
    copy_tree(work / "_build", d / "files" / "local.test")
    manifest(d, "https://local.test/index.html", "local.test/index.html")


def mkdocs(out, venv):
    work = out / "_src_mkdocs"
    shutil.rmtree(work, ignore_errors=True)
    (work / "docs").mkdir(parents=True)
    (work / "mkdocs.yml").write_text("site_name: Demo\ntheme:\n  name: material\nmarkdown_extensions:\n"
                                     "  - admonition\n  - pymdownx.superfences\n  - pymdownx.tabbed:\n"
                                     "      alternate_style: true\n  - tables\n")
    (work / "docs" / "index.md").write_text(MD)
    subprocess.run([str(venv / "mkdocs"), "build", "-q", "-f", str(work / "mkdocs.yml"), "-d", str(work / "site")],
                   check=True)
    d = out / "mkdocs-material"
    copy_tree(work / "site", d / "files" / "local.test")
    manifest(d, "https://local.test/index.html", "local.test/index.html")


def esbuild(node, src_text, outfile, jsx=False):
    src = node / ("_entry.jsx" if jsx else "_entry.js")
    src.write_text(src_text)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(node / "node_modules/.bin/esbuild"), str(src), "--bundle", "--minify",
                    "--define:process.env.NODE_ENV=\"production\"", "--outfile=" + str(outfile)], check=True,
                   cwd=node)


def main():
    out, venv, node = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    sphinx(out, venv, "pydocs-theme", "python_docs_theme")
    sphinx(out, venv, "furo", "furo")
    mkdocs(out, venv)
    d = out / "mui-emotion" / "files" / "local.test"
    esbuild(node, MUI, d / "app.js", jsx=True)
    (d / "index.html").write_text('<!doctype html><meta charset=utf-8><title>MUI</title><div id=root></div>'
                                  '<script src="app.js"></script>')
    manifest(out / "mui-emotion", "https://local.test/index.html", "local.test/index.html")
    d = out / "lit-shadow" / "files" / "local.test"
    esbuild(node, LIT, d / "app.js")
    (d / "index.html").write_text(LIT_HTML)
    manifest(out / "lit-shadow", "https://local.test/index.html", "local.test/index.html")
    d = out / "bootstrap-form" / "files"
    (d / "local.test").mkdir(parents=True, exist_ok=True)
    (d / "cdn.local").mkdir(parents=True, exist_ok=True)
    shutil.copy(node / "node_modules/bootstrap/dist/css/bootstrap.min.css", d / "cdn.local" / "bootstrap.min.css")
    (d / "local.test" / "index.html").write_text(FORM_HTML)
    manifest(out / "bootstrap-form", "https://local.test/index.html", "local.test/index.html")
    print("built")


if __name__ == "__main__":
    main()
