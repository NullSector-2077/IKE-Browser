"""The user-script bridge accepts a script's messages only from the pages the
script runs on (1.1.18, security audit F6).

Until 1.1.18 only the script's secret token was checked: a page that got the
token (another script in the same world, a renderer bug) could act as the
script on any site - write the clipboard, open tabs, download, send
GM_xmlhttpRequest with the script's grants. Now I.K.E. also checks, in the
browser, that the address the message comes from is one of the frames the
page really has and matches the script's @match / @include and no @exclude.
Messages of the script on its own pages, and in frames of its sites inside
other pages, still work.
"""

from test_userscripts import run_scripts, script, server  # noqa: F401  (server is a fixture)

FORGE = """(function () {
  var T = __TOKENS__, S = __SIDS__, P = '\\u0001ike-gm:';
  function m(u, text) { console.info(P + T.clip + ':' + JSON.stringify({id: S.clip, op: 'clip', d: {text: text}, u: u})); }
  m(location.href, 'from a page the script does not run on');
  m('http://127.0.0.1:%d/page', 'claims a page it is not');
  m(undefined, 'says nothing');
  console.info(P + T.clip + ':' + JSON.stringify({id: S.clip, op: 'tab', d: {url: 'http://127.0.0.1:%d/tab'},
    u: 'http://127.0.0.1:%d/page'}));
})();"""


def test_a_stolen_token_does_nothing_on_another_site(run_ike, server):  # noqa: F811
    port, seen, port2, seen2 = server
    scripts = [script("clip", ["GM_setClipboard", "GM_openInTab"], match="http://127.0.0.1/*")]
    # localhost is another site: the script does not run there, the page has its token anyway
    out = run_scripts(run_ike, port, scripts, ["http://localhost:%d/page" % port],
                      {"0": [FORGE % (port, port2, port)]})
    assert out["clipboard"] == "untouched", out["clipboard"]
    assert not any(u.endswith("/tab") for u in out["tabs"]), out["tabs"]


def test_the_script_still_works_on_its_own_pages(run_ike, server):  # noqa: F811
    port, seen, port2, seen2 = server
    scripts = [script("clip", ["GM_setClipboard"], match="http://127.0.0.1/*",
                      body="GM_setClipboard('from the script');")]
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/page" % port])
    assert out["clipboard"] == "from the script", out["clipboard"]


def test_the_script_works_in_a_frame_of_its_site(run_ike, server):  # noqa: F811
    port, seen, port2, seen2 = server
    scripts = [script("clip", ["GM_setClipboard"], match="http://127.0.0.1/*",
                      body="if (window.top !== window) GM_setClipboard('from the frame');")]
    frame = ("var f = document.createElement('iframe'); f.src = 'http://127.0.0.1:%d/page';"
             "document.body.appendChild(f);" % port)
    out = run_scripts(run_ike, port, scripts, ["http://localhost:%d/page" % port],
                      {"0": [frame] + ["void 0"] * 8})          # about 2.5 s for the frame and its script
    assert out["clipboard"] == "from the frame", out["clipboard"]
