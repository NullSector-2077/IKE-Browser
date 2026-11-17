// I.K.E. reader mode: keeps the main article and drops everything else.
// Returns true when an article was found and the page was rewritten.
// Light, sepia or dark and the size of the text are chosen on the page (1.1.5).
(function () {
  'use strict';
  function textLen(el) {
    var n = 0, ps = el.querySelectorAll('p');
    for (var i = 0; i < ps.length; i++) n += ps[i].textContent.trim().length;
    return n;
  }
  var best = null, bestScore = 0;
  var cands = document.querySelectorAll('article, main, [role="main"], [itemprop="articleBody"], div, section');
  for (var i = 0; i < cands.length; i++) {
    var el = cands[i];
    var len = textLen(el);
    if (len < 400) continue;
    var links = 0, as = el.querySelectorAll('a');
    for (var j = 0; j < as.length; j++) links += as[j].textContent.length;
    var total = el.textContent.length || 1;
    // prefer dense text, penalise link lists and huge wrappers
    var score = len * (1 - Math.min(0.9, links / total)) / Math.sqrt(1 + el.querySelectorAll('div').length);
    if (/^(ARTICLE|MAIN)$/.test(el.tagName)) score *= 1.5;
    if (score > bestScore) { bestScore = score; best = el; }
  }
  if (!best) return false;
  var title = (document.querySelector('h1') || {}).textContent || document.title;
  var copy = best.cloneNode(true);
  var junk = copy.querySelectorAll('script, style, noscript, nav, aside, form, iframe, button, ' +
    'footer, header nav, svg, [aria-hidden="true"], [class*="share"], [class*="social"], ' +
    '[class*="related"], [class*="comment"], [class*="advert"], [class*="newsletter"]');
  for (var k = 0; k < junk.length; k++) junk[k].remove();
  var all = copy.querySelectorAll('*');
  for (var m = 0; m < all.length; m++) {
    all[m].removeAttribute('style');
    all[m].removeAttribute('class');
    all[m].removeAttribute('id');
  }
  var h1 = copy.querySelector('h1');
  if (h1) h1.remove();
  // I.K.E. passes the reader settings and the labels in IKE_READER (features.py)
  var R = (typeof IKE_READER === 'object' && IKE_READER) || {};
  var theme = /^(auto|light|sepia|dark)$/.test(R.theme) ? R.theme : 'auto';
  var size = Math.max(14, Math.min(28, parseInt(R.size, 10) || 19));
  var L = R.labels || {};
  var words = (copy.textContent || '').trim().split(/\s+/).length;
  var css = ':root{color-scheme:light dark}' +
    'body{margin:0;background:Canvas;color:CanvasText;font:19px/1.65 Georgia,"Noto Serif",serif}' +
    'html[data-theme=light] body{background:#fbfbf8;color:#1d1d1f}html[data-theme=light]{color-scheme:light}' +
    'html[data-theme=sepia] body{background:#f4ecd8;color:#5b4636}html[data-theme=sepia]{color-scheme:light}' +
    'html[data-theme=dark] body{background:#1c1c1e;color:#e6e6e6}html[data-theme=dark]{color-scheme:dark}' +
    'body main{font-size:var(--ike-size,19px)}' +
    '.ike-meta{font:13px/1.4 system-ui,"Noto Sans",sans-serif;opacity:.65;margin:-.4em 0 2em}' +
    '.ike-tools{position:fixed;top:12px;right:14px;display:flex;gap:4px;padding:4px;border-radius:999px;' +
    'background:color-mix(in srgb,currentColor 8%,transparent);font:13px system-ui,"Noto Sans",sans-serif;z-index:9}' +
    '.ike-tools button{border:0;border-radius:999px;min-width:30px;height:28px;padding:0 8px;cursor:pointer;' +
    'background:transparent;color:inherit;font:inherit}' +
    '.ike-tools button:hover,.ike-tools button:focus-visible{background:color-mix(in srgb,currentColor 14%,transparent);outline:none}' +
    '.ike-tools button[aria-pressed=true]{background:color-mix(in srgb,currentColor 22%,transparent)}' +
    '.ike-tools .sw{width:14px;height:14px;border-radius:50%;display:inline-block;vertical-align:-2px;' +
    'border:1px solid color-mix(in srgb,currentColor 40%,transparent)}' +
    '@media print{.ike-tools{display:none}}' +
    'main{max-width:42em;margin:0 auto;padding:48px 24px 96px}' +
    'h1{font:600 1.9em/1.25 system-ui,"Noto Sans",sans-serif;margin:0 0 .8em}' +
    'h2,h3,h4{font-family:system-ui,"Noto Sans",sans-serif;line-height:1.3;margin:1.6em 0 .5em}' +
    'img,video,figure{max-width:100%;height:auto;margin:1em 0}figcaption{font-size:.8em;opacity:.7}' +
    'a{color:LinkText}pre,code{font-size:.85em;overflow:auto}blockquote{margin:1em 0;padding-left:1em;border-left:3px solid GrayText}';
  document.head.innerHTML = '<meta charset="utf-8"><title></title><style>' + css + '</style>';
  document.title = title;
  var main = document.createElement('main');
  var h = document.createElement('h1');
  h.textContent = title.trim();
  main.appendChild(h);
  if (R.tools !== false && L.minutes) {
    var meta = document.createElement('div');
    meta.className = 'ike-meta';
    meta.textContent = location.hostname + '  ·  ' + L.minutes.replace('%d', String(Math.max(1, Math.round(words / 220))));
    main.appendChild(meta);
  }
  main.appendChild(copy);
  document.body.innerHTML = '';
  document.body.removeAttribute('class');
  document.body.removeAttribute('style');
  document.documentElement.removeAttribute('class');
  document.body.appendChild(main);
  function apply() {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    main.style.setProperty('--ike-size', size + 'px');
  }
  function save() {
    if (R.prefix) console.log(R.prefix + JSON.stringify({ theme: theme, size: size }));
  }
  apply();
  if (R.tools !== false) {
    // light, sepia or dark, and the size of the text; I.K.E. remembers the choice
    var bar = document.createElement('div');
    bar.className = 'ike-tools';
    var buttons = [];
    function button(label, title, run, pressed) {
      var b = document.createElement('button');
      b.type = 'button';
      if (label.nodeType) b.appendChild(label); else b.textContent = label;
      b.title = title || '';
      b.setAttribute('aria-label', title || '');
      b.addEventListener('click', function () { run(); apply(); save(); refresh(); });
      b._pressed = pressed;
      buttons.push(b);
      bar.appendChild(b);
      return b;
    }
    function swatch(bg) {
      var s = document.createElement('span');
      s.className = 'sw';
      s.style.background = bg;
      return s;
    }
    function refresh() {
      buttons.forEach(function (b) { if (b._pressed) b.setAttribute('aria-pressed', String(b._pressed())); });
    }
    button('A\u2212', L.smaller, function () { size = Math.max(14, size - 1); });
    button('A+', L.larger, function () { size = Math.min(28, size + 1); });
    button(swatch('#fbfbf8'), L.light, function () { theme = theme === 'light' ? 'auto' : 'light'; },
           function () { return theme === 'light'; });
    button(swatch('#f4ecd8'), L.sepia, function () { theme = theme === 'sepia' ? 'auto' : 'sepia'; },
           function () { return theme === 'sepia'; });
    button(swatch('#1c1c1e'), L.dark, function () { theme = theme === 'dark' ? 'auto' : 'dark'; },
           function () { return theme === 'dark'; });
    refresh();
    document.body.appendChild(bar);
  }
  window.scrollTo(0, 0);
  return true;
})();
