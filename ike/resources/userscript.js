// I.K.E. user script host. One copy of this wrapper is built for every
// installed script, with its description (CFG) and its code filled in
// (preceded by the libraries it @requires). The wrapper decides whether the
// script applies to this document, gives it only the GM functions its @grant
// lines ask for (CFG.allow; GM_info always) and keeps a failing script from
// affecting anything else.
//
// A script in the page's own world is injected when the document is created,
// before any code of the page: it keeps here the original functions it needs
// to talk to I.K.E. (the page may replace them later) and then waits for its
// @run-at moment (CFG.defer). Its secret token (CFG.token, only for scripts
// granted a function that needs I.K.E.) never leaves this closure except
// through the original console.info.
(function () {
  var CFG = __US_CFG__;
  var href = location.href;
  if (!/^https?:/i.test(href)) return;
  if (CFG.noframes && window.top !== window) return;
  function hit(list) {
    for (var i = 0; i < list.length; i++) {
      try { if (new RegExp(list[i], 'i').test(href)) return true; } catch (e) {}
    }
    return false;
  }
  if (!hit(CFG.inc) || hit(CFG.exc)) return;
  var O = { say: console.info.bind(console), str: JSON.stringify, parse: JSON.parse,
    define: Object.defineProperty, keys: Object.keys, URL: URL, wait: setTimeout.bind(window),
    listen: EventTarget.prototype.addEventListener, call: Function.prototype.call,
    random: crypto.getRandomValues.bind(crypto) };

  var api = (function () {
    'use strict';
    var values = CFG.values || {}, pending = {}, counter = 0;
    var hasOwn = Object.prototype.hasOwnProperty;
    function has(name) { return CFG.allow.indexOf(name) >= 0; }
    function send(op, d) {
      if (!CFG.token) return;
      try { O.say(CFG.token + O.str({ id: CFG.id, op: op, d: d })); } catch (e) {}
    }
    if (has('xmlhttprequest')) {
      try {           // answers to GM_xmlhttpRequest: cannot be replaced by the page
        O.define(window, CFG.cb, { configurable: false, writable: false, enumerable: false,
          value: function (rid, data) {
            var f = pending[rid];
            if (f) { delete pending[rid]; f(data); }
          } });
      } catch (e) {}
    }
    function newId() {
      counter += 1;
      var r = new Uint32Array(4);
      O.random(r);
      return counter + '-' + r[0].toString(36) + r[1].toString(36) + r[2].toString(36) + r[3].toString(36);
    }
    function call(fn, arg) { if (typeof fn === 'function') { try { fn(arg); } catch (e) { fail(e); } } }
    function fail(e) {
      try { console.error('[I.K.E. user script] ' + CFG.name + ': ' + (e && e.stack || e)); } catch (x) {}
    }

    function getValue(k, def) {
      if (!hasOwn.call(values, k)) return def;
      try { return O.parse(values[k]); } catch (e) { return def; }
    }
    function setValue(k, v) {
      var s;
      try { s = O.str(v); } catch (e) { return; }
      if (s === undefined) { deleteValue(k); return; }
      values[String(k)] = s;
      send('set', { k: String(k), v: s });
    }
    function deleteValue(k) { delete values[String(k)]; send('del', { k: String(k) }); }
    function listValues() { return O.keys(values); }

    function addStyle(css) {
      var s = document.createElement('style');
      s.textContent = String(css);
      (document.head || document.documentElement).appendChild(s);
      return s;
    }
    function addElement(parent, tag, attrs) {
      if (typeof parent === 'string') { attrs = tag; tag = parent; parent = document.head || document.documentElement; }
      var el = document.createElement(tag);
      Object.keys(attrs || {}).forEach(function (k) {
        if (k === 'textContent') el.textContent = attrs[k]; else el.setAttribute(k, attrs[k]);
      });
      parent.appendChild(el);
      return el;
    }

    function bytes(b64) {
      var bin = atob(b64 || ''), out = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out;
    }
    function response(d, r, url) {
      var rt = d.responseType, o = { status: r.status, statusText: r.statusText, readyState: 4,
        responseHeaders: r.headers || '', finalUrl: r.url || url, context: d.context,
        responseText: r.text === undefined ? '' : r.text };
      if (rt === 'json') { try { o.response = JSON.parse(o.responseText); } catch (e) { o.response = null; } }
      else if (rt === 'arraybuffer') o.response = bytes(r.b64).buffer;
      else if (rt === 'blob') o.response = new Blob([bytes(r.b64)], { type: r.type || '' });
      else o.response = o.responseText;
      return o;
    }
    function sameOrigin(d, url) {            // the page's own request: its cookies apply
      var x = new XMLHttpRequest(), rt = d.responseType;
      x.open(d.method || 'GET', url, true, d.user, d.password);
      if (rt === 'json' || rt === 'arraybuffer' || rt === 'blob') x.responseType = rt;
      Object.keys(d.headers || {}).forEach(function (k) {
        try { x.setRequestHeader(k, d.headers[k]); } catch (e) {}
      });
      if (d.timeout) x.timeout = d.timeout;
      if (d.overrideMimeType) x.overrideMimeType(d.overrideMimeType);
      function snap() {
        var o = { status: x.status, statusText: x.statusText, readyState: x.readyState,
          responseHeaders: x.readyState >= 2 ? x.getAllResponseHeaders() : '', finalUrl: x.responseURL || url,
          context: d.context };
        try { o.response = x.response; } catch (e) {}
        try { o.responseText = x.responseText; } catch (e) { o.responseText = ''; }
        return o;
      }
      ['load', 'error', 'timeout', 'abort', 'progress', 'loadend', 'readystatechange'].forEach(function (n) {
        if (typeof d['on' + n] === 'function') x.addEventListener(n, function () { call(d['on' + n], snap()); });
      });
      x.send(d.data === undefined ? null : d.data);
      return { abort: function () { x.abort(); } };
    }
    function xmlhttpRequest(d) {
      d = d || {};
      var url;
      try { url = new O.URL(String(d.url), href); } catch (e) { call(d.onerror, { error: 'bad address', status: 0 }); return { abort: function () {} }; }
      if (url.origin === location.origin && !d.anonymous) return sameOrigin(d, url.href);
      var rid = newId(), live = true;
      if (window.top !== window) {           // answers can only reach the page itself
        setTimeout(function () { call(d.onerror, { error: 'not available inside frames', status: 0, readyState: 4, finalUrl: url.href, context: d.context }); }, 0);
        return { abort: function () {} };
      }
      pending[rid] = function (r) {
        if (!live) return;
        if (!r || r.error) {
          call(r && r.timeout ? d.ontimeout : d.onerror,
            { error: r ? r.error : 'failed', status: 0, statusText: '', readyState: 4, finalUrl: url.href, context: d.context });
        } else {
          var o = response(d, r, url.href);
          call(d.onreadystatechange, o);
          call(d.onload, o);
        }
        call(d.onloadend, { readyState: 4, context: d.context });
      };
      var body = d.data;
      if (body !== undefined && body !== null && typeof body !== 'string') {
        try { body = body instanceof URLSearchParams ? body.toString() : O.str(body); } catch (e) { body = String(body); }
      }
      send('xhr', { rid: rid, method: String(d.method || 'GET').toUpperCase(), url: url.href,
        headers: d.headers || {}, data: body === undefined ? null : body,
        binary: d.responseType === 'arraybuffer' || d.responseType === 'blob', timeout: +d.timeout || 0 });
      return { abort: function () { live = false; delete pending[rid]; call(d.onabort, {}); } };
    }

    function setClipboard(text) { send('clip', { text: String(text) }); }
    function openInTab(url, opt) {
      var background = opt === true || !!(opt && (opt.active === false || opt.loadInBackground));
      try { send('tab', { url: new O.URL(String(url), href).href, background: background }); } catch (e) {}
      return { close: function () {}, closed: false };
    }
    function notification(a, b, c, d) {
      var o = typeof a === 'object' && a ? a : { text: a, title: b, onclick: d };
      send('notify', { text: String(o.text || ''), title: String(o.title || CFG.name) });
      if (typeof o.ondone === 'function') setTimeout(o.ondone, 0);
    }
    function download(a, b) {
      var o = typeof a === 'object' && a ? a : { url: a, name: b };
      try { send('download', { url: new O.URL(String(o.url), href).href }); } catch (e) {}
      return { abort: function () {} };
    }
    function getResourceText(name) {
      var r = (CFG.resources || {})[name];
      return r ? r.text : null;
    }
    function getResourceURL(name) {
      var r = (CFG.resources || {})[name];
      return r ? 'data:' + (r.type || 'application/octet-stream') + ';base64,' + r.b64 : null;
    }
    var commands = [];
    function registerMenuCommand(name, fn) { commands.push([name, fn]); return commands.length; }
    function unregisterMenuCommand() {}
    function log() { console.log.apply(console, ['[' + CFG.name + ']'].concat([].slice.call(arguments))); }

    var info = { script: { name: CFG.name, namespace: CFG.namespace, version: CFG.version,
      description: CFG.description, matches: CFG.matches, grant: CFG.grant, 'run-at': CFG.runAt },
      scriptHandler: 'I.K.E.', version: CFG.ice, scriptMetaStr: CFG.meta };
    function later(fn) {
      return function () {
        var args = arguments;
        return new Promise(function (ok, no) { try { ok(fn.apply(null, args)); } catch (e) { no(e); } });
      };
    }
    // only what @grant asks for: [name in the GM object, function, granted name]
    var GM = { info: info }, all = [['getValue', later(getValue), 'getvalue'],
      ['setValue', later(setValue), 'setvalue'], ['deleteValue', later(deleteValue), 'deletevalue'],
      ['listValues', later(listValues), 'listvalues'], ['addStyle', later(addStyle), 'addstyle'],
      ['addElement', later(addElement), 'addelement'], ['setClipboard', later(setClipboard), 'setclipboard'],
      ['openInTab', later(openInTab), 'openintab'], ['notification', later(notification), 'notification'],
      ['getResourceUrl', later(getResourceURL), 'getresourceurl'],
      ['registerMenuCommand', later(registerMenuCommand), 'registermenucommand'],
      ['xmlHttpRequest', function (d) {
        return new Promise(function (ok, no) {
          d = Object.assign({}, d);
          var onload = d.onload, onerror = d.onerror;
          d.onload = function (r) { call(onload, r); ok(r); };
          d.onerror = function (r) { call(onerror, r); no(r); };
          xmlhttpRequest(d);
        });
      }, 'xmlhttprequest']];
    for (var i = 0; i < all.length; i++) if (has(all[i][2])) GM[all[i][0]] = all[i][1];
    function pick(name, f) { return has(name) ? f : undefined; }
    return { fail: fail, GM: GM, info: info, getValue: pick('getvalue', getValue),
      setValue: pick('setvalue', setValue), deleteValue: pick('deletevalue', deleteValue),
      listValues: pick('listvalues', listValues), addStyle: pick('addstyle', addStyle),
      addElement: pick('addelement', addElement), xmlhttpRequest: pick('xmlhttprequest', xmlhttpRequest),
      setClipboard: pick('setclipboard', setClipboard), openInTab: pick('openintab', openInTab),
      notification: pick('notification', notification), download: pick('download', download),
      getResourceText: pick('getresourcetext', getResourceText),
      getResourceURL: pick('getresourceurl', getResourceURL),
      registerMenuCommand: pick('registermenucommand', registerMenuCommand),
      unregisterMenuCommand: pick('unregistermenucommand', unregisterMenuCommand), log: pick('log', log) };
  })();

  var run = function (GM, GM_info, GM_getValue, GM_setValue, GM_deleteValue, GM_listValues,
      GM_addStyle, GM_addElement, GM_xmlhttpRequest, GM_setClipboard, GM_openInTab,
      GM_notification, GM_download, GM_getResourceText, GM_getResourceURL,
      GM_registerMenuCommand, GM_unregisterMenuCommand, GM_log, unsafeWindow, CFG, api, run, hit, href,
      O, start) {
__US_CODE__
  };
  function start() {
    try {
      O.call.call(run, window, api.GM, api.info, api.getValue, api.setValue, api.deleteValue,
        api.listValues, api.addStyle, api.addElement, api.xmlhttpRequest, api.setClipboard,
        api.openInTab, api.notification, api.download, api.getResourceText, api.getResourceURL,
        api.registerMenuCommand, api.unregisterMenuCommand, api.log, window);
    } catch (e) { api.fail(e); }
  }
  // @run-at for scripts injected at document creation, like the engine's own
  // moments: "end" after DOMContentLoaded, "idle" when the page has loaded or
  // 500 ms after DOMContentLoaded, whichever comes first. The listeners are
  // the first ones registered, so the page cannot stop them.
  var started = false;
  function go() { if (!started) { started = true; O.wait(start, 0); } }
  if (!CFG.defer) start();
  else if (CFG.defer === 'end') {
    if (document.readyState !== 'loading') go();
    else O.call.call(O.listen, window, 'DOMContentLoaded', go, true);
  } else if (document.readyState === 'complete') go();
  else {
    var ready = function () { O.wait(go, 500); };
    O.call.call(O.listen, window, 'load', go, true);
    if (document.readyState !== 'loading') ready();
    else O.call.call(O.listen, window, 'DOMContentLoaded', ready, true);
  }
})();
