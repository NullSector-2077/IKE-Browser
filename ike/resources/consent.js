// I.K.E. cookie-banner handler: refuses consent automatically where possible.
// Runs in an isolated world. __IKE_CFG__ is replaced at injection time.
(function () {
  'use strict';
  var CFG = __IKE_CFG__;
  if (window.top !== window && !/consent|cmp|privacy|cookie/i.test(location.hostname)) return;
  var host = location.hostname;
  function off(h) {
    while (h) {
      if (CFG.off.indexOf(h) >= 0) return true;
      var i = h.indexOf('.');
      if (i < 0) break;
      h = h.slice(i + 1);
    }
    return false;
  }
  if (off(host)) return;

  // Known consent platforms: selectors of their "reject all" buttons.
  var KNOWN = [
    '#onetrust-reject-all-handler', '.ot-pc-refuse-all-handler',
    '#CybotCookiebotDialogBodyButtonDecline',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll',
    '#didomi-notice-disagree-button', '.didomi-continue-without-agreeing',
    '.qc-cmp2-summary-buttons button[mode="secondary"]',
    '[data-testid="uc-deny-all-button"]',
    '#truste-consent-required', '.truste-button3',
    '.iubenda-cs-reject-btn',
    '.cmplz-btn.cmplz-deny', '.cky-btn-reject', '.osano-cm-denyAll', '.osano-cm-deny',
    '.cn-decline', '.klaro .cm-btn-decline', '[data-cookiefirst-action="reject"]',
    '#cookiescript_reject', '.cc-btn.cc-deny', '.cc-deny',
    '.fc-cta-do-not-consent', '#wt-cli-reject-btn', '.cli_action_button[data-cli_action="reject"]',
    '#cookie_action_close_header_reject', '.js-cookie-consent-reject',
    '[data-borlabs-cookie-actions="refuse"], .brlbs-btn-refuse, ._brlbs-refuse-btn a',
    '#hs-eu-decline-button', '.termly-styles-declineAll', '[data-tid="banner-decline"]',
    '#axeptio_btn_dismiss', '.sp_choice_type_13', 'button.sp_choice_type_REJECT_ALL',
    '#ccc-reject-settings', '#ccc-notify-reject', '.eu-cookie-compliance-reject-button',
    'button[data-cky-tag="reject-button"]', '#usercentrics-button-deny',
    'tp-yt-paper-button[aria-label^="Reject"], button[aria-label^="Reject all"]',
    'button[aria-label^="Rifiuta tutto"], button[aria-label^="Rifiuta l"]',
    'form[action*="consent.google"] button[aria-label^="Rifiuta"], form[action*="consent.google"] button[aria-label^="Reject"]',
    'button#W0wltc'
  ];
  var WORDS = /^(rifiuta( tutt[oi])?( e chiudi)?|rifiuto|rifiuta tutti i cookie|nega|non accetto|continua senza accettare|solo (cookie )?necessari|usa solo (i )?cookie necessari|accetta solo (i )?necessari|reject( all)?( cookies)?|decline( all)?|deny( all)?|refuse( all)?|i (do not|don't) accept|disagree|only (necessary|essential)( cookies)?|use (necessary|essential) cookies only|necessary (cookies )?only|essential (cookies )?only|continue without accepting|alle ablehnen|ablehnen|nur notwendige( cookies)?|tout refuser|refuser|continuer sans accepter|rechazar( todo| todas)?|rechazar cookies|denegar)$/i;
  var CONTAINER = /cookie|consent|gdpr|privacy|cmp|banner|notice/i;

  function visible(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function deepQuery(root, sel) {
    var found = null;
    try { found = root.querySelector(sel); } catch (e) { return null; }
    if (found) return found;
    var hosts = ['#usercentrics-root', '#cmpwrapper', 'aside#usercentrics-cmp-ui'];
    for (var i = 0; i < hosts.length; i++) {
      var h = document.querySelector(hosts[i]);
      if (h && h.shadowRoot) {
        try { found = h.shadowRoot.querySelector(sel); } catch (e) {}
        if (found) return found;
      }
    }
    return null;
  }
  function tryKnown() {
    for (var i = 0; i < KNOWN.length; i++) {
      var el = deepQuery(document, KNOWN[i]);
      if (el && visible(el)) { el.click(); return true; }
    }
    return false;
  }
  function inConsentBox(el) {
    for (var p = el, d = 0; p && p !== document.body && d < 12; p = p.parentElement, d++) {
      var tag = (p.id || '') + ' ' + (typeof p.className === 'string' ? p.className : '') +
        ' ' + (p.getAttribute('aria-label') || '');
      if (CONTAINER.test(tag)) return true;
      if (p.getAttribute('role') === 'dialog' && /cookie/i.test(p.textContent.slice(0, 3000))) return true;
    }
    return false;
  }
  function tryGeneric() {
    var btns = document.querySelectorAll('button, a[role="button"], [role="button"], input[type="button"], a.button, a.btn');
    for (var i = 0; i < btns.length && i < 600; i++) {
      var b = btns[i];
      var text = (b.innerText || b.value || '').replace(/\s+/g, ' ').trim();
      if (text.length < 3 || text.length > 45) continue;
      if (WORDS.test(text) && visible(b) && inConsentBox(b)) { b.click(); return true; }
    }
    return false;
  }
  var tries = 0, done = false;
  function attempt() {
    if (done) return;
    tries++;
    if (tryKnown() || tryGeneric()) { done = true; return; }
    if (tries < 24) setTimeout(attempt, tries < 8 ? 400 : 1000);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attempt);
  } else {
    attempt();
  }
})();
