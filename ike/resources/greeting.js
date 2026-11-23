/* The greeting of the new tab page (1.1.24), worked out here from the computer's clock, the week of
   the page's language and the weather the page already has. Nothing is asked of the network. The
   little it remembers (days of use, the streak, the usual hour, the version seen, which messages
   were shown) is kept in I.K.E.'s own settings and never leaves the computer (ike/greeting.py,
   "state"). The words come from I.K.E. as data (D.s), the pool of messages is here: a table of
   groups, each with a weight and the messages that fit the moment. A message comes again only
   after the others of its group were shown (a shuffled bag per group), and not within
   COOL days of its last showing. */
(function () {
  "use strict";
  var DAY = 86400000, HOLD = 2 * 3600000, COOL = 3;

  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function ymd(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function dayNo(d) { return Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY); }
  function parseDay(s) {
    var m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || "");
    return m ? Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3]) / DAY) : null;
  }
  function periodOf(h) {
    return h >= 5 && h < 12 ? "morning" : h >= 12 && h < 18 ? "afternoon" : h >= 18 && h < 23 ? "evening" : "night";
  }

  // ---- the week of the language, summer time, the hemisphere, the seasons (see 1.1.24's first version)
  function weekOf(lang) {
    try {
      var loc = new Intl.Locale(lang), wi = loc.getWeekInfo ? loc.getWeekInfo() : loc.weekInfo;
      if (wi && wi.firstDay && wi.weekend && wi.weekend.length) return {first: wi.firstDay, weekend: wi.weekend};
    } catch (e) {}
    return {first: 1, weekend: [6, 7]};
  }
  function dayBefore(d) { return (d - 2 + 7) % 7 + 1; }
  function workStart(w) {
    var d = w.first;
    for (var i = 0; i < 7; i++) { if (w.weekend.indexOf(d) < 0) return d; d = d % 7 + 1; }
    return w.first;
  }
  function beforeWeekend(w) {
    for (var i = 0; i < w.weekend.length; i++) {
      if (w.weekend.indexOf(dayBefore(w.weekend[i])) < 0) return dayBefore(w.weekend[i]);
    }
    return 0;
  }
  function hemisphere(d, h) {
    if (h) return h;
    var jan = new Date(d.getFullYear(), 0, 1).getTimezoneOffset(), jul = new Date(d.getFullYear(), 6, 1).getTimezoneOffset();
    return jan > jul ? 1 : jan < jul ? -1 : 0;
  }
  function seasonOf(m, n, h) {
    if (n != 1 || !h || [3, 6, 9, 12].indexOf(m) < 0) return null;
    var north = {3: "spring", 6: "summer", 9: "autumn", 12: "winter"}[m];
    return h == 1 ? north : {spring: "autumn", summer: "winter", autumn: "spring", winter: "summer"}[north];
  }

  // ---- holidays: only the traditions the user chose (D.hol), the day itself
  function easter(y, julian) {
    var a, b, c, d, e, f, g, h, i, k, l, m, mo, da;
    if (julian) {
      a = y % 4; b = y % 7; c = y % 19; d = (19 * c + 15) % 30; e = (2 * a + 4 * b - d + 34) % 7;
      mo = Math.floor((d + e + 114) / 31); da = (d + e + 114) % 31 + 1;
      return new Date(y, mo - 1, da + 13);                 // 13 days between the calendars, 1900-2099
    }
    a = y % 19; b = Math.floor(y / 100); c = y % 100; d = Math.floor(b / 4); e = b % 4;
    f = Math.floor((b + 8) / 25); g = Math.floor((b - f + 1) / 3); h = (19 * a + b - d - g + 15) % 30;
    i = Math.floor(c / 4); k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7; m = Math.floor((a + 11 * h + 22 * l) / 451);
    mo = Math.floor((h + l - 7 * m + 114) / 31); da = (h + l - 7 * m + 114) % 31 + 1;
    return new Date(y, mo - 1, da);
  }
  var fmts = {};
  // the day in another calendar of the engine's own (ICU) data: {m: month, d: day}
  function inCalendar(cal, date, long) {
    try {
      var key = cal + (long ? "L" : "N");
      var f = fmts[key] || (fmts[key] = new Intl.DateTimeFormat("en-u-ca-" + cal + "-nu-latn",
        {day: "numeric", month: long ? "long" : "numeric"}));
      var out = {};
      f.formatToParts(new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12)).forEach(function (p) {
        if (p.type === "month") out.m = p.value;
        if (p.type === "day") out.d = +p.value;
      });
      return out.d ? out : null;
    } catch (e) { return null; }
  }
  function same(a, b) { return a.getFullYear() == b.getFullYear() && a.getMonth() == b.getMonth() && a.getDate() == b.getDate(); }
  // the word key of the holiday of this day, or "" (the traditions chosen, the tables of dates)
  function holidayOn(d, chosen, tab) {
    var y = d.getFullYear(), m = d.getMonth() + 1, n = d.getDate(), x, has = function (t) { return chosen.indexOf(t) >= 0; };
    tab = tab || {};
    if (has("civil") && m == 1 && n == 1) return "newyear";
    if (has("christian")) {
      if (m == 12 && n == 25) return "christmas";
      if (same(d, easter(y, false))) return "easter";
    }
    if (has("orthodox")) {
      if (m == 1 && n == 7) return "christmas";
      if (same(d, easter(y, true))) return "easter";
    }
    if (has("islamic")) {                                   // Umm al-Qura: a day either way of the local sighting
      x = inCalendar("islamic-umalqura", d, false);
      if (x && x.m == "9" && x.d == 1) return "ramadan";
      if (x && x.m == "10" && x.d == 1) return "eid";
      if (x && x.m == "12" && x.d == 10) return "eid";
    }
    if (has("jewish")) {                                    // the day itself (the holiday begins the evening before)
      x = inCalendar("hebrew", d, true);
      if (x && /^tish/i.test(x.m) && x.d == 1) return "shana";
      if (x && /^tish/i.test(x.m) && x.d == 10) return "kippur";
      if (x && /^kisl/i.test(x.m) && x.d == 25) return "hanukkah";
      if (x && /^nisan/i.test(x.m) && x.d == 15) return "passover";
    }
    if (has("lunar")) {         // the listed years first (the engine is a day off in some), else the engine's calendar
      var listed = (tab.lunarny || []).filter(function (t) { return t.slice(0, 4) == "" + y; });
      if (listed.length) { if (listed.indexOf(ymd(d)) >= 0) return "lunarny"; }
      else {
        x = inCalendar("chinese", d, false);
        if (x && x.m == "1" && x.d == 1) return "lunarny";
      }
    }
    if (has("nowruz") && m == 3 && n == 21) return "nowruz";
    var day = ymd(d);
    if (has("hindu")) {
      if ((tab.diwali || []).indexOf(day) >= 0) return "diwali";
      if ((tab.holi || []).indexOf(day) >= 0) return "holi";
    }
    if (has("buddhist") && (tab.vesak || []).indexOf(day) >= 0) return "vesak";
    return "";
  }

  // ---- the pool: [group, weight(c), [[key, fits(c)], ...]]
  function yes() { return true; }
  var W = function (c, k) { return c.w && c.w.k == k; };
  var GROUPS = [
    ["updated", function (c) { return c.upd ? 100 : 0; }, [["updated", yes]]],
    ["away", function (c) { return c.first && c.gap >= 3 ? 10 : 0; }, [["away", yes]]],
    ["welcome", function (c) { return c.first && c.gap >= 1 && c.gap < 3 ? 5 : 0; }, [["welcome", yes]]],
    ["streak", function (c) { return c.first && c.streak >= 3 ? 5 : 0; }, [
      ["streak3", function (c) { return c.streak >= 3; }], ["streak7", function (c) { return c.streak >= 7; }]]],
    ["late", function (c) { return c.hour >= 1 && c.hour < 5 ? 12 : 0; }, [["late", yes]]],
    ["dst", function (c) { return c.dst && c.hour >= 18 ? 8 : 0; }, [["dst", yes]]],
    ["season", function (c) { return c.season ? 8 : 0; }, [
      ["spring", function (c) { return c.season == "spring"; }], ["summer", function (c) { return c.season == "summer"; }],
      ["autumn", function (c) { return c.season == "autumn"; }], ["winter", function (c) { return c.season == "winter"; }]]],
    ["newmonth", function (c) { return c.date == 1 && !c.season ? 4 : 0; }, [["newmonth", yes]]],
    ["weather", function (c) { return 6; }, [
      ["rain", function (c) { return W(c, "rain"); }], ["snow", function (c) { return W(c, "snow"); }],
      ["fog", function (c) { return W(c, "fog"); }], ["wind", function (c) { return !!(c.w && c.w.wind); }],
      ["hot", function (c) { return !!(c.w && c.w.hot); }], ["cold", function (c) { return !!(c.w && c.w.cold); }],
      ["sun", function (c) { return W(c, "clear") && !!c.w.warm && c.hour >= 7 && c.hour < 19; }]]],
    ["week", function (c) { return 3; }, [
      ["week", function (c) { return c.day == workStart(c.week) && c.hour >= 5 && c.hour < 12; }],
      ["soon", function (c) { return c.day == beforeWeekend(c.week); }],
      ["weekend", function (c) { return c.week.weekend.indexOf(c.day) >= 0; }]]],
    ["period", function (c) { return 3; }, [
      ["morning1", function (c) { return c.p == "morning"; }], ["morning2", function (c) { return c.p == "morning"; }],
      ["afternoon1", function (c) { return c.p == "afternoon"; }], ["afternoon2", function (c) { return c.p == "afternoon"; }],
      ["evening1", function (c) { return c.p == "evening"; }], ["evening2", function (c) { return c.p == "evening"; }],
      ["night1", function (c) { return c.p == "night"; }], ["night2", function (c) { return c.p == "night"; }]]],
    ["fact", function (c) { return 2; }, [
      ["fact1", yes], ["fact2", yes], ["fact3", yes], ["fact4", yes], ["fact5", yes], ["fact6", yes],
      ["fact7", yes], ["fact8", yes], ["fact9", yes], ["fact10", yes], ["fact11", yes], ["fact12", yes]]],
    ["cheer", function (c) { return 2; }, [
      ["cheer1", yes], ["cheer2", yes], ["cheer3", yes], ["cheer4", yes], ["cheer5", yes],
      ["cheer6", yes], ["cheer7", yes], ["cheer8", yes], ["cheer9", yes], ["cheer10", yes]]]
  ];
  function groupKeys(g) { return g[2].map(function (m) { return m[0]; }); }
  function allKeys() {
    var out = [];
    GROUPS.forEach(function (g) { out = out.concat(groupKeys(g)); });
    return out;
  }
  function shuffle(a, rng) {
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  // the usage signals: kept locally, once per day; returns what the day's first opening looks like
  function usage(st, now, version) {
    var today = ymd(now), first = st.last !== today, gap = 0, changed = false;
    if (first) {
      var last = parseDay(st.last);
      gap = last === null ? -1 : Math.max(0, dayNo(now) - last);
      st.days = (st.days || 0) + 1;
      st.streak = gap === 1 ? (st.streak || 0) + 1 : 1;
      if (!st.first) st.first = today;
      var n = Math.min(st.hn || 0, 29), hr = now.getHours() + now.getMinutes() / 60;   // a running average of 30 days
      st.hour = Math.round((((st.hour || 0) * n + hr) / (n + 1)) * 100) / 100;
      st.hn = (st.hn || 0) + 1;
      st.last = today;
      changed = true;
    }
    if (version && st.ver !== version) {
      if (st.ver) { st.upd = today; st.updDone = ""; }            // not on a first installation
      st.ver = version;
      changed = true;
    }
    return {first: first, gap: gap, changed: changed};
  }

  function context(D, now, u) {
    var st = D.st, w = weekOf(D.lang), h = now.getHours(), tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 12);
    return {hour: h, p: periodOf(h), day: now.getDay() || 7, date: now.getDate(), week: w, w: D.w || {},
            first: u.first, gap: u.gap, streak: st.streak || 0, upd: !!(st.upd === ymd(now) && st.updDone !== D.v && D.v),
            dst: tomorrow.getTimezoneOffset() != new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12).getTimezoneOffset(),
            season: seasonOf(now.getMonth() + 1, now.getDate(), hemisphere(now, D.h))};
  }

  // the first key of the group's bag that fits and is not in its cooldown; a new shuffled bag when none is left
  function fromBag(g, st, c, today, rng) {
    var keys = groupKeys(g), fits = {};
    g[2].forEach(function (m) { fits[m[0]] = m[1](c); });
    st.bags = st.bags || {}; st.cool = st.cool || {};
    var bag = (st.bags[g[0]] || []).filter(function (k) { return keys.indexOf(k) >= 0; });
    function take() {
      var ok = bag.filter(function (k) { return fits[k]; });
      if (!ok.length) return null;
      var fresh = ok.filter(function (k) { return st.cool[k] === undefined || today - st.cool[k] >= COOL; });
      var k = (fresh.length ? fresh : ok)[0];
      bag.splice(bag.indexOf(k), 1);
      return k;
    }
    var k = take();
    if (k === null) {
      var last = st.cool && keys.sort(function (a, b) { return (st.cool[b] || 0) - (st.cool[a] || 0); })[0];
      bag = shuffle(groupKeys(g), rng);
      if (bag.length > 1 && bag[0] === last && st.cool[last] !== undefined) bag.push(bag.shift());     // not the one just shown, first
      k = take();
    }
    st.bags[g[0]] = bag;
    if (k !== null) st.cool[k] = today;
    return k;
  }

  // what to show now: {p, key, n, changed}; D: {st, w, h, v, tone, hol, tab, lang}
  function decide(D, now, rng) {
    rng = rng || Math.random;
    var st = D.st = D.st || {}, u = usage(st, now, D.v), c = context(D, now, u), today = dayNo(now), changed = u.changed;
    var hol = holidayOn(now, D.hol || [], D.tab);
    var out = {p: c.p, key: "", n: st.streak || 0, changed: false};
    if (hol) { out.key = hol; out.changed = changed; return out; }          // a holiday the user asked for: all day
    if (D.tone === "greetings") { out.changed = changed; return out; }
    var cur = st.cur;
    if (cur && cur.p === c.p && cur.d === ymd(now) && now.getTime() - cur.t < HOLD && cur.t <= now.getTime() &&
        allKeys().indexOf(cur.k) >= 0) {
      out.key = cur.k; out.changed = changed; return out;                   // the same line for a while
    }
    var cands = [], total = 0;
    GROUPS.forEach(function (g) {
      var wt = g[1](c);
      if (wt > 0 && g[2].some(function (m) { return m[1](c); })) { cands.push([g, wt]); total += wt; }
    });
    var r = rng() * total, g = cands[cands.length - 1];
    for (var i = 0; i < cands.length; i++) { r -= cands[i][1]; if (r < 0) { g = cands[i]; break; } }
    var k = g ? fromBag(g[0], st, c, today, rng) : null;
    if (k) {
      out.key = k;
      st.cur = {p: c.p, d: ymd(now), t: now.getTime(), k: k};
      if (k === "updated") st.updDone = D.v;
    }
    out.changed = true;
    return out;
  }

  // the page: writes the greeting, and again when the period changes; the state goes home by an
  // image request to I.K.E.'s own address (answered by I.K.E., refused to any web page)
  function create(D, els, save, rng) {
    var shown = null;
    function words(key, n) {
      return (D.s[key] || "").replace("%d", n).replace("{version}", D.v || "");
    }
    return {
      update: function (now) {
        var p = periodOf(now.getHours());
        if (shown === p) return;
        shown = p;
        var r = decide(D, now, rng);
        els.title(D.s[r.p] || "");
        els.line(r.key ? words(r.key, r.n) : "");
        if (r.changed && save) save(D.st);
      },
      setWeather: function (w) { D.w = w || {}; }
    };
  }

  // for the tests: the groups that fit a moment, with their weights and the lines that fit
  function options(c) {
    var out = [];
    GROUPS.forEach(function (g) {
      var wt = g[1](c), fit = g[2].filter(function (m) { return m[1](c); }).map(function (m) { return m[0]; });
      if (wt > 0 && fit.length) out.push([g[0], wt, fit]);
    });
    return out;
  }
  window.IkeGreeting = {create: create, decide: decide, holidayOn: holidayOn, easter: easter, keys: allKeys,
                        groups: function () { return GROUPS.map(function (g) { return [g[0], groupKeys(g)]; }); },
                        options: options, context: context, bag: function (name, st, c, today, rng) {
                          return fromBag(GROUPS.filter(function (g) { return g[0] === name; })[0], st, c, today, rng);
                        }, periodOf: periodOf, weekOf: weekOf, seasonOf: seasonOf, usage: usage};
})();
