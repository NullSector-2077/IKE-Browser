#!/usr/bin/env python3
"""The compatibility matrix from the results of run.py and baseline.js.

    matrix.py NAME=DIR [NAME=DIR ...]      (e.g. Kontrol=out/mx_strict Chrome140=out/bl_chrome)

Each site's own check (sites.json) gives a verdict: ok, part (the page works,
its main function was not reached), FAIL, env (a captcha, a geographic block
or a sign-in wall that the baseline browsers get too), "-" (not run).
"""
import json
import sys


def _v(ok, part=False):
    return "ok" if ok else ("part" if part else "FAIL")


def _video(c):
    if not isinstance(c, dict):
        return "FAIL"
    return _v(c.get("video") and c.get("advanced"), c.get("video"))


RULES = {
    "google_search": lambda c, p: "env" if c.get("captcha") else _v(c.get("results", 0) > 3),
    "gmail": lambda c, p: _v(c.get("email") or c.get("signin_link")) if not c.get("rejected") else "FAIL",
    "google_maps": lambda c, p: _v(c.get("search") and c.get("canvas", 0) > 0, c.get("search")),
    "google_earth": lambda c, p: "FAIL" if c.get("unsupported") else _v(c.get("canvas", 0) > 0),
    "google_drive": lambda c, p: _v(c.get("email") or c.get("landing")),
    "google_docs": lambda c, p: _v(c.get("email") or "Sign-in" in str(c.get("title"))),
    "google_translate": lambda c, p: _v(c.get("buongiorno")),
    "facebook": lambda c, p: _v(c.get("email") and c.get("pass")),
    "instagram": lambda c, p: _v(c.get("user") and c.get("pass")),
    "x": lambda c, p: "FAIL" if c.get("err") else _v((p.get("text") or 0) > 200),
    "x_profile": lambda c, p: "FAIL" if c.get("err") else _v(c.get("tweets", 0) > 0, (p.get("text") or 0) > 200),
    "reddit": lambda c, p: "env" if c.get("blocked") else _v(c.get("posts", 0) > 3),
    "whatsapp": lambda c, p: _v(c.get("qr"), (p.get("text") or 0) > 100),
    "telegram_k": lambda c, p: _v(c.get("qr") and c.get("text", 0) > 50),
    "telegram_a": lambda c, p: _v(c.get("qr") and c.get("text", 0) > 150, c.get("qr")),
    "discord": lambda c, p: _v(c.get("email") and (c.get("qr") or c.get("qrText")), c.get("email")),
    "teams": lambda c, p: "FAIL" if c.get("unsupported") else _v(c.get("email") or "login" in str(c.get("host"))),
    "youtube": lambda c, p: _video(c),
    "twitch": lambda c, p: _video(c),
    "dailymotion": lambda c, p: _v(c.get("video") and c.get("advanced"), c.get("video") or c.get("playerFrame")),
    "vimeo": lambda c, p: _video(c),
    "vimeo_player": lambda c, p: _video(c),
    "dailymotion_player": lambda c, p: _video(c),
    "spotify": lambda c, p: "FAIL" if c.get("unsupported") else _v(c.get("tracks", 0) > 0 and c.get("play")),
    "soundcloud": lambda c, p: _v(c.get("playing") or (c.get("audio", 0) > 0), c.get("button")),
    "raiplay": lambda c, p: _v(c.get("items", 0) > 3),
    "raiplay_live": lambda c, p: "env" if c.get("geo") else _video(c),
    "mediaset": lambda c, p: _v(c.get("items", 0) > 3, c.get("text", 0) > 200),
    "bitmovin": lambda c, p: _video(c),
    "shaka": lambda c, p: _video(c),
    "hlsjs": lambda c, p: _video(c),
    "amazon": lambda c, p: "env" if c.get("captcha") else _v(c.get("results", 0) > 3),
    "ebay": lambda c, p: "env" if c.get("challenge") else _v(c.get("results", 0) > 3),
    "aliexpress": lambda c, p: "env" if c.get("slider") and not c.get("results") else _v(c.get("results", 0) > 3),
    "booking": lambda c, p: "env" if c.get("challenge") and not c.get("results") else _v(c.get("results", 0) > 3),
    "paypal": lambda c, p: "env" if c.get("captcha") else _v(c.get("email")),
    "photopea": lambda c, p: _v(c.get("canvas", 0) > 0 and c.get("menus"), c.get("text", 0) > 50),
    "canva": lambda c, p: "env" if c.get("challenge") else _v(c.get("login") and c.get("text", 0) > 200),
    "github": lambda c, p: _v(c.get("readme")),
    "outlook": lambda c, p: _v(c.get("email") or c.get("signin")),
    "m365": lambda c, p: _v(c.get("signin") or c.get("text", 0) > 200),
    "chatgpt": lambda c, p: "env" if c.get("challenge") else _v(c.get("composer")),
    "claude": lambda c, p: "env" if c.get("challenge") else _v(c.get("email") or c.get("google")),
    "gemini": lambda c, p: _v(c.get("composer"), c.get("signin")),
}


def verdict(rec):
    p = rec.get("probe") or {}
    c = p.get("check")
    if not isinstance(c, dict):
        if isinstance(c, str) and c.startswith("EXC"):
            return "FAIL"
        return "FAIL" if not p else "?"
    rule = RULES.get(rec["key"])
    try:
        return rule(c, p) if rule else "?"
    except Exception:
        return "?"


def main():
    cols = [a.split("=", 1) for a in sys.argv[1:]]
    data = []
    for name, d in cols:
        try:
            data.append({r["key"]: r for r in json.load(open(d + "/results.json", encoding="utf-8"))})
        except FileNotFoundError:
            data.append({})
    keys = [k for D in data for k in D]
    keys = list(dict.fromkeys(keys))
    print("| site | " + " | ".join(n for n, _ in cols) + " |")
    print("|---" * (len(cols) + 1) + "|")
    for k in keys:
        row = [verdict(D[k]) if k in D else "-" for D in data]
        print("| %s | %s |" % (k, " | ".join(row)))


if __name__ == "__main__":
    main()
