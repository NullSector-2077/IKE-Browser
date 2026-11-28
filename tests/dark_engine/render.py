"""Renders the study's pages offscreen under several dark modes and saves, for each
page and mode, a screenshot (PNG) and what the page holds (JSON: rectangles of
text, media and checked elements, load times, the prototype's own counters).
Not part of the automatic tests.

    QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \\
        python3 tests/dark_engine/render.py OUT_DIR [--modes off,dr,native,proto] [--pages a,b]
            [--snaps DIR] [--bench N] [--loadtime N] [--speedometer DIR] [--live]

Modes: off (no dark mode), dr (Dark Reader, I.K.E.'s current engine, through
ike/darkpages.py as the browser installs it), native (Chromium's ForceDarkMode),
proto (the I.K.E. Dark Engine prototype, ike/darkengine.py).

Pages: the synthetic pages of pages.py, or with --snaps the snapshots of
snapshot.py / localsites.py, served from two local origins (the page's site on
one port, other sites on another), every other request blocked. --live loads
the snapshots' real addresses instead (where the network allows it).
Both dark engines get a stand-in of I.K.E.'s page bridge (passwords.py
PageBridge.fetchCss) that answers only addresses the page itself requested.
DE_SAME_ORIGIN_CSS=1 serves every style sheet from the page's own origin: Dark
Reader refuses to fetch a style sheet of another origin over http, on a port or
on 127.0.0.1 (darkreader.js shouldIgnoreCors), so only that way can it be
compared on the pages whose sheets come "from a CDN" here.
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
# a dark mode forced for every Chromium program of the computer (set for another
# browser) is taken away, as I.K.E. itself does (ike/app.py _strip_dark_flags):
# else "without dark mode" is the engine's own forced dark, and the Dark Engine
# runs on top of it
from ike.app import _strip_dark_flags, split_flags  # noqa: E402

_flags, FORCED_DARK = _strip_dark_flags(split_flags(os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]))
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(_flags)
if FORCED_DARK:
    print("a forced dark mode of the computer (QTWEBENGINE_CHROMIUM_FLAGS) is left out here, as in I.K.E.", flush=True)

import pages  # noqa: E402

CROSS_CSS = ("browserleaks", "eff-", "creepjs", "furo")     # their style sheets served as from a CDN

PROBE = r"""(function(){
function R(r){return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]}
function vis(r){return r.width>4&&r.height>4&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth}
var text=[],media=[],checks=[];
if(!document.body)return JSON.stringify({text:text,media:media,checks:checks});
var w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);var n;
while((n=w.nextNode())&&text.length<1500){if(!n.data.trim())continue;var p=n.parentElement;if(!p||/^(SCRIPT|STYLE|OPTION|NOSCRIPT)$/.test(p.tagName))continue;
 var cs=getComputedStyle(p);if(cs.visibility==='hidden'||+cs.opacity<0.3)continue;
 var rg=document.createRange();rg.selectNodeContents(n);var rs=rg.getClientRects();
 for(var i=0;i<rs.length;i++){var r=rs[i];if(vis(r))text.push(R(r));}}
document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea,select,button').forEach(function(e){var r=e.getBoundingClientRect();if(!vis(r))return;
 var t=e.value||e.placeholder||e.textContent.trim();if(t&&e.tagName!=='BUTTON')text.push([Math.round(r.left)+3,Math.round(r.top)+3,Math.min(Math.round(r.width)-6,8*t.length+8),Math.min(Math.round(r.height)-6,22)]);
 if(checks.length<120)checks.push({kind:'visible',rect:R(r),tag:e.tagName});});
document.querySelectorAll('[data-check]').forEach(function(e){checks.push({kind:e.dataset.check,rect:R(e.getBoundingClientRect()),tag:e.tagName})});
document.querySelectorAll('img,canvas,video,iframe,picture,svg,[data-media]').forEach(function(e){var r=e.getBoundingClientRect();if(!vis(r))return;
 if(e.dataset&&e.dataset.check){media.push(R(r));return;}
 if(e.tagName!=='svg'&&e.tagName!=='SVG')media.push(R(r));
 if(r.width<=64&&r.height<=64&&(e.tagName==='IMG'||e.tagName.toLowerCase()==='svg'))checks.push({kind:'visible',rect:R(r),tag:e.tagName});
 else if(r.width>=100&&r.height>=80&&/^(IMG|CANVAS|VIDEO)$/.test(e.tagName))checks.push({kind:'keep',rect:R(r),tag:e.tagName});});
var all=document.body.getElementsByTagName('*');for(var k=0;k<all.length&&k<6000;k++){var bi=getComputedStyle(all[k]).backgroundImage;
 if(bi&&bi.indexOf('url(')>=0){var r2=all[k].getBoundingClientRect();if(vis(r2))media.push(R(r2));}}
var nav=performance.getEntriesByType('navigation')[0]||{};
return JSON.stringify({text:text,media:media,checks:checks,dcl:Math.round(nav.domContentLoadedEventEnd||0),load:Math.round(nav.loadEventEnd||0)});})()"""

BRIDGE_JS = r"""
new QWebChannel(qt.webChannelTransport, function (channel) {
  var ike = channel.objects.ike;
  if (!ike) return;
  Object.defineProperty(window, '__ikeBridge', {value: Object.freeze({
    fetchCss: function (id, url) { ike.fetchCss(String(id), String(url)); },
    cssFetched: Object.freeze({connect: function (f) { ike.cssFetched.connect(f); }})
  })});
});
"""


# DE_DIAG=1: for the Dark Engine's pages, the large light areas left on the screen and
# where their colour comes from (a rule of a style sheet, an inline style, a sheet the
# page cannot read, a frame, a picture), to find why a part stayed light
DIAG = r"""(function(){
function rgba(s){var m=/rgba?\(([^)]+)\)/.exec(s||'');if(!m)return null;var p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);return [p[0],p[1],p[2],p.length>3?p[3]:1];}
function lum(c){function f(v){v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4)}return 0.2126*f(c[0])+0.7152*f(c[1])+0.0722*f(c[2]);}
function label(e){return e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(/\s+/).slice(0,3).join('.'):'');}
var sheets=[],unreadable=[];
for(var i=0;i<document.styleSheets.length;i++){var sh=document.styleSheets[i];try{sh.cssRules;sheets.push(sh);}catch(e){unreadable.push(sh.href||'(inline)');}}
(document.adoptedStyleSheets||[]).forEach(function(sh){sheets.push(sh);});
// every rule that gives this element a background picture or gradient, as the page has it now
function bgRules(el){var found=[];function walk(list,href){for(var j=0;j<list.length&&found.length<6;j++){var r=list[j];
 try{if(r.selectorText&&r.style&&(r.style.getPropertyValue('background-image')||r.style.getPropertyValue('background'))&&el.matches(r.selectorText))
  found.push((href||'inline/adopted')+' :: '+r.selectorText.slice(0,80)+' { background: '+(r.style.getPropertyValue('background')||'')+' ; background-image: '+r.style.getPropertyValue('background-image')+(r.style.getPropertyPriority('background-image')?' !important':'')+' }');
  else if(r.cssRules)walk(r.cssRules,href);}catch(e){}}}
 for(var k=0;k<sheets.length;k++)walk(sheets[k].cssRules,(sheets[k].href||'').slice(-60));
 var at=el.getAttribute('style');if(at&&/background/.test(at))found.push('style attribute: '+at.slice(0,200));
 return found;}
function rulesFor(el){var found=[];function walk(list,href){for(var j=0;j<list.length&&found.length<4;j++){var r=list[j];
 try{if(r.selectorText&&r.style&&(r.style.backgroundColor||r.style.background)&&el.matches(r.selectorText))found.push((href||'inline')+' :: '+r.selectorText.slice(0,80)+' { background: '+(r.style.backgroundColor||r.style.background).slice(0,60)+' }');
 else if(r.cssRules)walk(r.cssRules,href);}catch(e){}}}
 for(var k=0;k<sheets.length;k++)walk(sheets[k].cssRules,(sheets[k].href||'').slice(-60));return found;}
// where a variable used by a light area's rules gets its value: the element and
// its ancestors (a style attribute, a rule of a readable sheet), @property
function varsOf(list){var names={};list.forEach(function(s){var re=/var\(\s*(--[\w-]+)/g,m;while((m=re.exec(s)))names[m[1]]=1;});return Object.keys(names).slice(0,4);}
function definedAt(el,name){var res=[],props=[];
 function walk(list,href){for(var j=0;j<list.length;j++){var r=list[j];try{
  if(r.constructor&&r.constructor.name==='CSSPropertyRule'&&r.name===name)props.push('@property '+name+' initial-value '+r.initialValue+' inherits '+r.inherits+' ('+(href||'inline')+')');
  else if(r.selectorText&&r.style&&r.style.getPropertyValue(name))walkRule(r,href);
  else if(r.cssRules)walk(r.cssRules,href);}catch(e){}}}
 var chain=[];for(var a=el;a&&a.nodeType===1&&chain.length<20;a=a.parentElement)chain.push(a);
 function walkRule(r,href){for(var c=0;c<chain.length;c++){try{if(chain[c].matches(r.selectorText)){res.push('rule on '+label(chain[c])+' :: '+(href||'inline')+' :: '+r.selectorText.slice(0,80)+' { '+name+': '+r.style.getPropertyValue(name).trim().slice(0,60)+(r.style.getPropertyPriority(name)?' !important':'')+' }');return;}}catch(e){}}}
 for(var k=0;k<sheets.length&&res.length<6;k++)walk(sheets[k].cssRules,(sheets[k].href||'').slice(-60));
 for(var c=0;c<chain.length;c++){var at=chain[c].getAttribute('style')||'';if(at.indexOf(name)>=0)res.push('style attribute on '+label(chain[c])+': '+at.slice(Math.max(0,at.indexOf(name)-20),at.indexOf(name)+80));}
 return {name:name,value:getComputedStyle(el).getPropertyValue(name).trim().slice(0,80),where:res.slice(0,8),property:props.slice(0,2),
  ancestors:chain.slice(0,4).map(function(a){var o=a.outerHTML;return o.slice(0,o.indexOf('>')+1).slice(0,240);})};}
var out=[],all=document.querySelectorAll('body *'),W=innerWidth,H=innerHeight;
for(var i=0;i<all.length&&out.length<25;i++){var e=all[i],r=e.getBoundingClientRect();
 if(r.width*r.height<W*H*0.01||r.bottom+scrollY<0||r.top>H*6||r.right<0||r.left>W)continue;   // the page down to six screens, not only what is seen
 var cs=getComputedStyle(e);if(cs.visibility==='hidden'||+cs.opacity<0.3)continue;
 var bg=rgba(cs.backgroundColor),img=cs.backgroundImage;
 var light=bg&&bg[3]>0.5&&lum(bg)>0.5;
 if(!light&&(r.top>H||!(/^(IMG|IFRAME|CANVAS|VIDEO|EMBED|OBJECT)$/.test(e.tagName))))continue;
 out.push({el:label(e),rect:[Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)],
  bg:cs.backgroundColor,image:img.slice(0,80),inline:(e.getAttribute('style')||'').slice(0,120),
  shadowHost:!!e.shadowRoot,frame:e.tagName==='IFRAME'?(e.src||'(no src)').slice(0,80):null,rules:light?rulesFor(e):[]});
 var last=out[out.length-1];if(last.rules.length)last.vars=varsOf(last.rules).map(function(n){return definedAt(e,n);});}
// light text drawn over a picture (an <img> or a background picture under it, no
// opaque colour between): where a light photo kept its light under a text made light
var onpic=[],seenTxt=new Set();
var tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
for(var tn=tw.nextNode();tn&&onpic.length<15;tn=tw.nextNode()){
 if(!tn.data.trim())continue;var te=tn.parentElement;if(!te||seenTxt.has(te))continue;seenTxt.add(te);
 var tr=te.getBoundingClientRect();if(tr.width<20||tr.height<8||tr.bottom<0||tr.top>H||tr.right<0||tr.left>W)continue;
 var tc=rgba(getComputedStyle(te).color);if(!tc||lum(tc)<0.45)continue;
 var stack=document.elementsFromPoint(Math.min(W-1,Math.max(0,tr.left+tr.width/2)),Math.min(H-1,Math.max(0,tr.top+tr.height/2)));
 var past=false;
 for(var si=0;si<stack.length;si++){var se=stack[si];if(se===te||se.contains(te)){past=true;}if(!past&&!te.contains(se))continue;
  var ss=getComputedStyle(se),sb=rgba(ss.backgroundColor),pic=ss.backgroundImage.indexOf('url(')>=0?ss.backgroundImage:(se.tagName==='IMG'?(se.currentSrc||se.src):'');
  if(pic){onpic.push({text:tn.data.trim().slice(0,40),el:label(te),rect:[Math.round(tr.left),Math.round(tr.top),Math.round(tr.width),Math.round(tr.height)],
   color:getComputedStyle(te).color,under:label(se),picture:String(pic).slice(0,140)});break;}
  if(sb&&sb[3]>0.5)break;}}
// light text whose background, looked at layer by layer under it, is light: a colour,
// a gradient, a ::before/::after layer or an inset shadow (what a plain colour test misses)
var lowc=[],seenL=new Set();
function layerOf(se){var ss=getComputedStyle(se),r=[];
 ['::before','::after'].forEach(function(ps){var p=getComputedStyle(se,ps);if(p.content&&p.content!=='none'){var pb=rgba(p.backgroundColor);
  if((pb&&pb[3]>0.5)||p.backgroundImage!=='none')r.push({kind:ps,color:p.backgroundColor,image:p.backgroundImage.slice(0,120)});}});
 if(ss.backgroundImage!=='none')r.push({kind:'image',color:ss.backgroundColor,image:ss.backgroundImage.slice(0,160)});
 if(/inset/.test(ss.boxShadow))r.push({kind:'inset shadow',color:ss.boxShadow.slice(0,120)});
 var b=rgba(ss.backgroundColor);if(b&&b[3]>0.5)r.push({kind:'colour',color:ss.backgroundColor});return r;}
var tw2=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
for(var t2=tw2.nextNode();t2&&lowc.length<20;t2=tw2.nextNode()){
 if(!t2.data.trim())continue;var e2=t2.parentElement;if(!e2||seenL.has(e2))continue;seenL.add(e2);
 var r2=e2.getBoundingClientRect();if(r2.width<10||r2.height<8||r2.bottom<0||r2.top>H||r2.right<0||r2.left>W)continue;
 var c2=rgba(getComputedStyle(e2).color);if(!c2||lum(c2)<0.35)continue;
 var st2=document.elementsFromPoint(Math.min(W-1,Math.max(0,r2.left+Math.min(r2.width/2,40))),Math.min(H-1,Math.max(0,r2.top+r2.height/2)));
 var found=null,chain=[];
 for(var k2=0;k2<st2.length&&!found;k2++){var x2=st2[k2];if(x2!==e2&&!x2.contains(e2)&&!e2.contains(x2))continue;
  var ls=layerOf(x2);chain.push(label(x2));
  for(var m2=0;m2<ls.length&&!found;m2++){var L=ls[m2],lc=rgba(L.color);
   if(L.kind==='colour'){if(lum(lc)>0.5)found={layer:label(x2),kind:L.kind,value:L.color,rules:rulesFor(x2)};else{found='dark';}}
   else if(L.kind.charAt(0)===':'&&lc&&lc[3]>0.5&&lum(lc)>0.5)found={layer:label(x2)+L.kind,kind:L.kind,value:L.color,rules:rulesFor(x2)};
   else if(/gradient|url\(/.test(L.image||'')||L.kind==='inset shadow'){
    var gc=(L.image||L.color||'').match(/rgba?\([^)]*\)|#[0-9a-f]{3,8}\b|\bwhite\b/gi)||[];
    if(gc.some(function(c){var q=rgba(c)||(/white|#fff/i.test(c)?[255,255,255,1]:null);return q&&q[3]>0.3&&lum(q)>0.5;})||/url\(/.test(L.image||''))
     found={layer:label(x2),kind:L.kind,value:(L.image||L.color),inline:(x2.getAttribute('style')||'').slice(0,120),rules:bgRules(x2)};}}}
 if(found&&found!=='dark')lowc.push({text:t2.data.trim().slice(0,40),el:label(e2),rect:[Math.round(r2.left),Math.round(r2.top),Math.round(r2.width),Math.round(r2.height)],
  color:getComputedStyle(e2).color,under:found,path:chain.slice(0,6)});}
return JSON.stringify({light:out,onpicture:onpic,lowcontrast:lowc,unreadable:unreadable.slice(0,20),sheets:document.styleSheets.length,
 adopted:document.adoptedStyleSheets.length,frames:document.querySelectorAll('iframe').length});})()"""


def serve(snaps, speedo):
    imgs = pages.images()
    docs = dict(pages.PAGES, bench=pages.BENCH)
    docs.update(getattr(pages, "EXTRA", {}))
    ports = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            p = self.path.split("?")[0].strip("/")
            body = ctype = None
            if p.startswith("img/") and p[4:] in imgs:
                body, ctype = imgs[p[4:]], "image/png"
            elif p.removesuffix(".html") in docs:
                body, ctype = docs[p.removesuffix(".html")].encode(), "text/html; charset=utf-8"
            elif p.startswith("snap/") and snaps:
                body, ctype = self.snap(p[5:])
            elif p.startswith("speedometer/") and speedo:
                f = (Path(speedo) / p[12:]).resolve()
                if p.endswith("/") or f.is_dir():
                    f = f / "index.html"
                if f.is_file() and str(f).startswith(str(Path(speedo).resolve())):
                    body, ctype = f.read_bytes(), mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=600")
            self.end_headers()
            self.wfile.write(body)

        def snap(self, rest):
            name, _, path = rest.partition("/")
            from urllib.parse import unquote
            base = Path(snaps) / name / "files"
            f = base / unquote(path)
            if not f.is_file() and (base / (unquote(path) + "/index.html")).is_file():
                f = base / (unquote(path) + "/index.html")
            if not f.is_file():
                f = base / path
            if not f.is_file():
                return None, None
            data = f.read_bytes()
            ctype = mimetypes.guess_type(str(f).split("@")[0])[0]
            if not ctype:
                head = data[:300].lstrip().lower()
                ctype = "text/html" if head.startswith((b"<!doctype", b"<html", b"<")) else "application/octet-stream"
            if f.name == "index" or ctype.startswith("text/") or ctype.endswith(("javascript", "json", "svg+xml")):
                text = data.decode("utf-8", "replace")
                tp = ports["fp"] if os.environ.get("DE_SAME_ORIGIN_CSS") else ports["tp"]
                text = text.replace("__FP__", str(ports["fp"])).replace("__TP__", str(tp))
                if ctype == "text/html" or f.name == "index":
                    ctype = "text/html"
                    if any(name.startswith(c) for c in CROSS_CSS) and not os.environ.get("DE_SAME_ORIGIN_CSS"):
                        def cross(m):
                            href = m.group(2)
                            if href.startswith("http://127.0.0.1:%d/" % ports["fp"]):
                                href = href.replace(":%d/" % ports["fp"], ":%d/" % ports["tp"])
                            elif not href.startswith(("http:", "https:", "//", "data:")):
                                d = "/".join(("snap/" + rest).split("/")[:-1])
                                href = "http://127.0.0.1:%d/%s/%s" % (ports["tp"], d, href)
                            return m.group(1) + href + m.group(3)
                        text = re.sub(r'(<link[^>]*rel=["\']?stylesheet["\']?[^>]*href=["\'])([^"\']+)(["\'])', cross, text)
                        text = re.sub(r'(<link[^>]*href=["\'])([^"\']+\.css[^"\']*)(["\'][^>]*rel=["\']?stylesheet)', cross, text)
                data = text.encode()
                ctype += "; charset=utf-8"
            return data, ctype

        def log_message(self, *a):
            pass

    for k in ("fp", "tp"):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        ports[k] = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return ports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--modes", default="off,dr,native,proto")
    ap.add_argument("--pages", default="")
    ap.add_argument("--snaps", default="")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--bench", type=int, default=0, help="runs of the speed proxy per mode (0: none)")
    ap.add_argument("--bench-only", action="store_true", help="skip screenshots and run only the speed proxy")
    ap.add_argument("--loadtime", type=int, default=0, help="loads per page and mode, times only")
    ap.add_argument("--speedometer", default="", help="a Speedometer checkout: run it once per mode")
    ap.add_argument("--settle", type=int, default=0, help="ms to wait after the load")
    ap.add_argument("--size", default="")
    a = ap.parse_args()
    if a.bench_only and (a.bench < 1 or a.loadtime or a.speedometer):
        ap.error("--bench-only requires a positive --bench count")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import (
        QWebEngineLoadingInfo,
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineScript,
        QWebEngineSettings,
        QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, msg, line, src):
            if os.environ.get("DE_DEBUG") or msg.startswith("[ike-de]"):
                print("console:", msg, line, src[-40:], flush=True)

    class Guard(QWebEngineUrlRequestInterceptor):
        """Records what the pages request; with snapshots, nothing leaves this computer."""
        def __init__(self, local_only):
            super().__init__()
            self.local_only, self.seen, self.blocked = local_only, set(), 0

        def interceptRequest(self, info):
            u = info.requestUrl()
            if self.local_only and u.scheme() in ("http", "https", "ws", "wss") and u.host() != "127.0.0.1":
                info.block(True)
                self.blocked += 1
                return
            self.seen.add(u.toString())

    class Bridge(QObject):
        """Stand-in of I.K.E.'s PageBridge.fetchCss: only addresses the page requested itself."""
        cssFetched = pyqtSignal(str, bool, str)

        def __init__(self, guard, log):
            super().__init__()
            self.guard, self.log = guard, log

        @pyqtSlot(str, str)
        def fetchCss(self, ident, url):
            ok, text = False, ""
            if url in self.guard.seen:
                try:
                    with urllib.request.urlopen(url, timeout=15) as r:
                        text, ok = r.read(3 << 20).decode("utf-8", "replace"), True
                except Exception:  # noqa: BLE001
                    pass
                self.log["fetched"] += 1
            else:
                self.log["refused"] += 1
                self.log.setdefault("refused_urls", []).append(url)
            QTimer.singleShot(0, lambda: self.cssFetched.emit(ident, ok, text))

    app = QApplication(sys.argv[:1])
    ports = serve(a.snaps, a.speedometer)
    base = "http://127.0.0.1:%d/" % ports["fp"]
    modes = a.modes.split(",")
    if a.snaps:
        names = a.pages.split(",") if a.pages else sorted(
            p.name for p in Path(a.snaps).iterdir() if (p / "manifest.json").exists())
    else:
        names = a.pages.split(",") if a.pages else list(pages.PAGES)
    size = a.size or ("1280x900" if a.snaps else "%dx%d" % (pages.W, pages.H))
    width, height = (int(x) for x in size.split("x"))
    settle = a.settle or (2500 if a.snaps else 1500)
    jobs = []
    if a.speedometer:
        jobs += [(m, "speedometer", "speedo") for m in modes]
    elif a.loadtime:
        jobs += [(m, n, "time") for _ in range(a.loadtime) for m in modes for n in names]
    elif not a.bench_only:
        jobs += [(m, n, "shot") for m in modes for n in names]
    jobs += [(m, "bench", "bench") for m in modes for _ in range(a.bench)]
    results = {"bench": {}, "times": {}, "speedometer": {}, "bridge": {}, "errors": []}
    profiles = {}
    qwc = QFile(":/qtwebchannel/qwebchannel.js")
    qwc.open(QIODevice.OpenModeFlag.ReadOnly)
    qwc_src = bytes(qwc.readAll()).decode("utf-8")
    state = {"view": None}

    def url_of(name):
        if name == "speedometer":
            return base + "speedometer/index.html?startAutomatically=true", "http://127.0.0.1/", None
        if a.snaps and name != "bench":
            m = json.loads((Path(a.snaps) / name / "manifest.json").read_text())
            if a.live and m.get("site") != "local.test":
                return m["url"], m["url"], m.get("expected_content")
            return base + "snap/%s/%s" % (name, m["entry"]), m["url"], m.get("expected_content")
        return base + name + ".html", base + name + ".html", None

    def profile_for(mode):
        if mode not in profiles:
            prof = QWebEngineProfile(app)          # off the record
            guard = Guard(bool(a.snaps) and not a.live)
            prof.setUrlRequestInterceptor(guard)
            log = results["bridge"].setdefault(mode, {"fetched": 0, "refused": 0})
            s = QWebEngineScript()
            s.setName("bridge")
            s.setSourceCode(qwc_src + BRIDGE_JS)
            s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            s.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            s.setRunsOnSubFrames(False)
            prof.scripts().insert(s)
            if mode.startswith("proto"):
                from ike import darkengine
                # DE_JS_<mode>=file: a variant of darkengine.js for that mode (A/B of a change)
                variant = os.environ.get("DE_JS_" + mode)
                if variant:
                    from ike import darkfixes
                    common = json.dumps(darkengine._fix(darkfixes.common_fix()))
                    src = Path(variant).read_text("utf-8").replace("__IKE_DE_COMMON__", common)
                    prof.scripts().insert(darkengine._script(darkengine._NAME, src))
                    darkengine._state[id(prof)] = {"sites": {}, "order": []}
                else:
                    darkengine.install(prof)
            profiles[mode] = (prof, guard, log)
        return profiles[mode]

    def next_job():
        if state["view"] is not None:
            state["view"].deleteLater()
            state["view"] = None
        if not jobs:
            for p, g, _ in profiles.values():
                results.setdefault("blocked", 0)
                results["blocked"] += g.blocked
            (out / "results.json").write_text(json.dumps(results, indent=1))
            app.exit(bool(results["errors"]))
            return
        mode, name, kind = jobs.pop(0)
        if kind == "shot":
            for ext in ("png", "json"):
                (out / f"{name}__{mode}.{ext}").unlink(missing_ok=True)
        prof, guard, log = profile_for(mode)
        url, orig, expected_content = url_of(name)
        if mode == "dr":
            from drcompare import darkpages as _drp
            darkpages = _drp()
            darkpages.prepare(prof, orig, "127.0.0.1" if not a.live else QUrl(orig).host(),
                              {"brightness": 100, "contrast": 100, "sepia": 0}, True, False)
        if mode.startswith("proto"):
            from ike import darkengine
            darkengine.prepare(prof, orig, "127.0.0.1" if not a.live else QUrl(orig).host(), True, False)
        view = QWebEngineView()
        page = Page(prof, view)
        view.setPage(page)
        if mode.startswith("proto"):
            # as I.K.E. does (webview.py set_backdrop): before the page paints, the
            # window shows the engine's dark background, not Qt's white
            from PyQt6.QtGui import QColor

            from ike import darkengine as _de
            page.setBackgroundColor(QColor(_de.background(None)))
        channel = QWebChannel(page)
        bridge = Bridge(guard, log)
        channel.registerObject("ike", bridge)
        page.setWebChannel(channel, QWebEngineScript.ScriptWorldId.ApplicationWorld)
        page._keep = (channel, bridge)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, mode == "native")
        view.resize(width if kind != "speedo" else 1400, height if kind != "speedo" else 1000)
        view.show()
        state["view"] = view
        job = {"loaded": False, "finished": False}

        def finish(error=None):
            if job["finished"]:
                return
            job["finished"] = True
            if error:
                results["errors"].append({"page": name, "mode": mode, "kind": kind, "error": error})
                print("error", mode, name, error, flush=True)
            QTimer.singleShot(0, next_job)

        def loaded(info):
            status = info.status()
            final = QWebEngineLoadingInfo.LoadStatus
            if status not in (final.LoadSucceededStatus, final.LoadFailedStatus):
                return
            if job["loaded"] or job["finished"]:
                return
            job["loaded"] = True
            code = info.errorCode()
            if info.errorDomain() == QWebEngineLoadingInfo.ErrorDomain.HttpStatusCodeDomain and code >= 400:
                finish(f"HTTP {code}")
                return
            if status == final.LoadFailedStatus:
                finish(f"navigation failed ({info.errorDomain().name} {code})")
                return
            job["status"] = code
            if kind == "bench":
                QTimer.singleShot(settle, lambda: page.runJavaScript(
                    "bench().then(function(t){window.__bt=t})", 0, lambda _: QTimer.singleShot(200, poll)))
            elif kind == "speedo":
                QTimer.singleShot(5000, speedo)
            elif kind == "time":
                QTimer.singleShot(1500, timing)
            else:
                QTimer.singleShot(settle, click_then_shoot)

        # DE_CLICK=text: a button or link with that text is clicked first (a site's
        # age or cookie question), then the page is given the time to settle again
        # DE_SCROLL=1: the page is scrolled down six screens and back first, as a
        # reader does, so that what a page loads only when it is reached is there
        def scroll_then_shoot():
            if job["finished"]:
                return
            if not os.environ.get("DE_SCROLL"):
                shoot()
                return
            page.runJavaScript(
                "(function(){var i=0,h=innerHeight;var t=setInterval(function(){i++;scrollTo(0,i*h/2);"
                "if(i>=12){clearInterval(t);setTimeout(function(){scrollTo(0,0)},800);}},300);})()", 0,
                lambda _: None if job["finished"] else QTimer.singleShot(6000, shoot))

        def click_then_shoot():
            if job["finished"]:
                return
            text = os.environ.get("DE_CLICK", "")
            if not text:
                scroll_then_shoot()
                return
            page.runJavaScript(
                "(function(t){t=t.toLowerCase();var es=document.querySelectorAll('button,a,[role=button],input[type=submit]');"
                "for(var i=0;i<es.length;i++){var s=(es[i].innerText||es[i].value||'').trim().toLowerCase();"
                "if(s&&s.indexOf(t)>=0){es[i].click();return true;}}return false;})(%s)" % json.dumps(text), 0,
                lambda clicked: None if job["finished"] else (
                    print("clicked", mode, name, bool(clicked), flush=True),
                    QTimer.singleShot(max(settle, 4000), scroll_then_shoot)))

        def poll():
            if job["finished"]:
                return
            def got(v):
                if job["finished"]:
                    return
                if v is None:
                    QTimer.singleShot(100, poll)
                else:
                    results["bench"].setdefault(mode, []).append(round(v, 1))

                    def stats(e):
                        print("bench", mode, round(v, 1), "engine:", e, flush=True)
                        finish()
                    if mode.startswith("proto"):
                        page.runJavaScript("JSON.stringify(window.__ikeDEStats||null)", 1, stats)
                    else:
                        stats(None)
            page.runJavaScript("window.__bt", 0, got)

        def speedo():
            if job["finished"]:
                return
            def got(v):
                if job["finished"]:
                    return
                if not v:
                    QTimer.singleShot(5000, speedo)
                    return
                results["speedometer"][mode] = v
                print("speedometer", mode, v, flush=True)
                # a profiling variant of the engine (DE_JS_<mode>) may sum its time in the top window
                page.runJavaScript("JSON.stringify(window.__ikeDEProf||null)", 1,
                                   lambda p: p and p != "null" and print("profile", mode, p, flush=True))
                view.grab().toImage().save(str(out / ("speedometer__%s.png" % mode)))
                finish()
            page.runJavaScript("(function(){var e=document.querySelector('#result-number');"
                               "var s=document.querySelector('#summary');"
                               "return e&&e.textContent.trim()&&s&&s.offsetParent!==null?"
                               "e.textContent.trim()+' '+(document.querySelector('#confidence-number')||{}).textContent:''})()",
                               0, got)

        def timing():
            def got(js):
                if job["finished"]:
                    return
                if not js:
                    finish("navigation timing unavailable")
                    return
                d = json.loads(js)
                results["times"].setdefault(name, {}).setdefault(mode, []).append([d.get("dcl"), d.get("load")])
                print("time", mode, name, d.get("dcl"), d.get("load"), flush=True)
                finish()
            page.runJavaScript("(function(){var n=performance.getEntriesByType('navigation')[0]||{};"
                               "return JSON.stringify({dcl:Math.round(n.domContentLoadedEventEnd||0),"
                               "load:Math.round(n.loadEventEnd||0)})})()", 0, got)

        def shoot():
            if job["finished"]:
                return
            def probed(js):
                if job["finished"]:
                    return
                if not js:
                    finish("expected content missing" if expected_content else "render probe unavailable")
                    return
                d = json.loads(js)

                def stats(v):
                    if job["finished"]:
                        return
                    img = view.grab().toImage()
                    if not img.save(str(out / ("%s__%s.png" % (name, mode)))):
                        finish("could not save screenshot")
                        return
                    d["engine"] = v
                    d["http_status"] = job["status"]
                    if job.get("flash"):
                        d["flash"] = job["flash"]
                        print("flash", mode, name, json.dumps(job["flash"]), flush=True)
                    (out / ("%s__%s.json" % (name, mode))).write_text(json.dumps(d))
                    print("shot", mode, name, "engine:", v, flush=True)
                    if mode.startswith("proto") and os.environ.get("DE_DIAG"):
                        def diag(js2):
                            (out / ("%s__%s.diag.json" % (name, mode))).write_text(js2 or "null")
                            finish()
                        page.runJavaScript(DIAG, 0, diag)
                        return
                    finish()
                if mode.startswith("proto"):
                    page.runJavaScript("JSON.stringify(window.__ikeDEStats||null)", 1, lambda v: stats(json.loads(v or "null")))
                else:
                    stats(None)
            probe = PROBE
            if expected_content:
                probe = f"document.querySelector({json.dumps(expected_content)}) && ({probe})"
            page.runJavaScript(probe, 0, probed)

        page.loadingChanged.connect(loaded)
        # DE_FLASH=1: while the page arrives, a picture every 50 ms for 4 s: how much
        # of the window is light (a white flash before the page is darkened) and when
        if os.environ.get("DE_FLASH") and kind == "shot":
            t_load = time.monotonic()
            flash = job.setdefault("flash", {"max": 0.0, "at": None, "frames": 0, "light_frames": 0})

            def sample():
                if job["finished"] or time.monotonic() - t_load > 4.0:
                    return
                img = view.grab().toImage()
                w, h = img.width(), img.height()
                if w > 8 and h > 8:
                    light = total = 0
                    for yy in range(6, h, max(1, h // 30)):
                        for xx in range(6, w, max(1, w // 40)):
                            c = img.pixelColor(xx, yy)
                            total += 1
                            if 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue() > 180:
                                light += 1
                    share = light / max(1, total)
                    flash["frames"] += 1
                    if share > 0.25:
                        flash["light_frames"] += 1
                    if share > flash["max"]:
                        flash["max"], flash["at"] = round(share, 3), int((time.monotonic() - t_load) * 1000)
                QTimer.singleShot(50, sample)
            QTimer.singleShot(0, sample)
        page.load(QUrl(url))
        def slow():
            # a page that never stops loading (live video, endless requests): its
            # picture is taken as it is after 20 s, not given up
            if job["loaded"] or job["finished"]:
                return
            if kind == "shot":
                job["loaded"] = True
                job["status"] = 0
                print("still loading after 20 s, taken as it is:", mode, name, flush=True)
                t_ask = time.monotonic()
                # how long the page takes to answer a script (a page kept busy shows here)
                page.runJavaScript("1", 0, lambda _: print("page answered a script after %.1f s:" % (time.monotonic() - t_ask),
                                                            mode, name, flush=True))
                if mode.startswith("proto"):
                    # what the engine did meanwhile (its own time, batches, looks at the page, pictures)
                    page.runJavaScript("JSON.stringify(window.__ikeDEStats||null)", 1,
                                       lambda v: print("engine while busy:", mode, name, v, flush=True))
                QTimer.singleShot(settle, click_then_shoot)
            else:
                finish("navigation timed out")
        QTimer.singleShot(20000, slow)
        QTimer.singleShot(3000000 if kind == "speedo" else 120000 + 2 * settle,
                          lambda: finish("measurement timed out"))

    QTimer.singleShot(0, next_job)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
