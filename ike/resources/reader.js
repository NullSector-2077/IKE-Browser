// I.K.E. reader mode: keeps the main article and drops everything else.
// Returns true when an article was found and the page was rewritten.
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
  var css = ':root{color-scheme:light dark}' +
    'body{margin:0;background:Canvas;color:CanvasText;font:19px/1.65 Georgia,"Noto Serif",serif}' +
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
  main.appendChild(copy);
  document.body.innerHTML = '';
  document.body.removeAttribute('class');
  document.body.removeAttribute('style');
  document.documentElement.removeAttribute('class');
  document.body.appendChild(main);
  window.scrollTo(0, 0);
  return true;
})();
