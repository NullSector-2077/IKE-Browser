// I.K.E. video-ad fallback for YouTube-style players (isolated world).
// The list rules normally stop an ad from being scheduled at all. When one
// slips through, this script makes it invisible and gets rid of it:
//  - a style sheet, present before the player exists, hides the video and
//    the ad interface for as long as the player reports an ad, so no ad
//    frame is ever painted;
//  - the ad is muted and fast-forwarded to its end;
//  - the "skip" button is activated by the page fallback and, when embedded,
//    its coordinates are relayed to I.K.E.'s top-frame Qt input bridge.
// An ad that cannot be skipped stays muted and visually concealed until the
// player leaves its ad state; the previous 5-second reveal exposed the ad.
// The script lives in the profile and is limited to the hosts below, both as
// a page and as a frame embedded in another site.
// __ICE_VA__ is replaced with {hosts: [...]}.
(function () {
  'use strict';
  var CFG = __ICE_VA__;
  var hn = location.hostname, ok = false;
  for (var i = 0; i < CFG.hosts.length; i++) {
    var h = CFG.hosts[i];
    if (hn === h || hn.slice(-h.length - 1) === '.' + h) ok = true;
  }
  if (!ok) return;
  CFG.frame = window.top !== window;
  if (window.__iceVideoAds) return;
  window.__iceVideoAds = true;

  var AD = '.html5-video-player.ad-showing, .html5-video-player.ad-interrupting';
  var SKIP = '.ytp-skip-ad-button, .ytp-ad-skip-button, .ytp-ad-skip-button-modern, ' +
             '.ytp-ad-skip-button-slot button, .ytp-ad-skip-button-container button';
  var CLUTTER = '.ytp-ad-overlay-container, .ytp-ad-message-container, #player-ads, ' +
                '#masthead-ad, ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, ' +
                'ytd-promoted-sparkles-web-renderer, ytd-banner-promo-renderer';
  var CSS =
    '.html5-video-player.ad-showing video,' +
    '.html5-video-player.ad-interrupting video,' +
    '.html5-video-player.ad-showing .video-ads,' +
    '.html5-video-player.ad-interrupting .video-ads,' +
    '.html5-video-player.ad-showing .ytp-ad-module,' +
    '.html5-video-player.ad-interrupting .ytp-ad-module,' +
    '.html5-video-player.ad-showing .ytp-ad-player-overlay,' +
    '.html5-video-player.ad-interrupting .ytp-ad-player-overlay,' +
    '.html5-video-player.ad-showing .ytp-ad-player-overlay-layout,' +
    '.html5-video-player.ad-interrupting .ytp-ad-player-overlay-layout' +
    '{opacity:0!important}' +
    CLUTTER + '{display:none!important}';

  function addStyle() {
    var root = document.head || document.documentElement;
    if (!root) return false;
    if (document.getElementById('ice-videoads')) return true;
    var s = document.createElement('style');
    s.id = 'ice-videoads';
    s.textContent = CSS;
    root.appendChild(s);
    return true;
  }
  if (!addStyle()) {
    new MutationObserver(function (_m, o) { if (addStyle()) o.disconnect(); })
      .observe(document, { childList: true, subtree: true });
  }

  var state = null;             // set while an ad is being handled
  var watched = new WeakSet();  // players and videos already being watched
  var timer = 0, fast = false;

  function schedule(quick) {
    if (timer && fast === quick) return;
    if (timer) clearInterval(timer);
    fast = quick;
    timer = setInterval(tick, quick ? 120 : 500);
  }

  function realClick(btn) {
    var now = Date.now();
    if (now - state.lastClick < 700) return;
    var r = btn.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return;
    var x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) return;
    var hit = document.elementFromPoint(x, y);
    if (!hit || (hit !== btn && !btn.contains(hit))) return;
    state.lastClick = now;
    if (CFG.frame) {
      // Cross-origin frames cannot access the browser bridge. Send only the
      // click point and viewport size; the top-frame relay validates the
      // sender against an actual YouTube iframe before forwarding it to Qt.
      try {
        window.top.postMessage({
          type: 'ice-video-ad-skip', x: x, y: y,
          viewportWidth: window.innerWidth, viewportHeight: window.innerHeight
        }, '*');
      } catch (e) {}
      return;
    }
    var bridge = window.__iceBridge;
    if (bridge && typeof bridge.adClick === 'function') bridge.adClick(x, y);
  }

  function restore() {
    var s = state;
    state = null;
    if (!s) return;
    if (s.video) {
      try {
        if (s.muted !== null) s.video.muted = s.muted;
        if (s.rate) s.video.playbackRate = s.rate;
      } catch (e) {}
    }
    if (s.player) s.player.removeAttribute('data-ice-ad');
    schedule(false);
  }

  function act() {
    var player = document.querySelector(AD);
    if (!player) { if (state) restore(); return; }
    var video = player.querySelector('video');
    if (!state) {
      state = { since: Date.now(), player: player, video: video, lastClick: 0,
                muted: video ? video.muted : null, rate: 0 };
      player.setAttribute('data-ice-ad', 'skipping');
      schedule(true);
    }
    if (video) {
      if (state.video !== video) { state.video = video; state.muted = video.muted; }
      try {
        video.muted = true;
        if (isFinite(video.duration) && video.duration > 0) {
          if (video.currentTime < video.duration - 0.1) video.currentTime = video.duration;
        } else if (video.playbackRate < 16) {
          if (!state.rate) state.rate = video.playbackRate || 1;
          video.playbackRate = 16;
        }
      } catch (e) {}
    }
    var btn = player.querySelector(SKIP) || document.querySelector(SKIP);
    if (btn && Date.now() - state.lastClick >= 700) {
      try { btn.click(); } catch (e) {}
      realClick(btn);
    }
  }

  function watch() {
    var players = document.querySelectorAll('.html5-video-player');
    for (var i = 0; i < players.length; i++) {
      var p = players[i];
      if (!watched.has(p)) {
        watched.add(p);
        new MutationObserver(act).observe(p, { attributes: true, attributeFilter: ['class'] });
      }
      var v = p.querySelector('video');
      if (v && !watched.has(v)) {
        watched.add(v);
        ['loadedmetadata', 'durationchange', 'playing', 'timeupdate'].forEach(function (n) {
          v.addEventListener(n, function () { if (state || document.querySelector(AD)) act(); }, true);
        });
      }
    }
  }

  function tick() { watch(); act(); }
  schedule(false);
  tick();
})();
