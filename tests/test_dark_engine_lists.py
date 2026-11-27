"""The part of Dark Reader's fixes the I.K.E. Dark Engine uses
(darkfixes.engine_css): no rule that needs Dark Reader's own output is given to
the engine, and nearly all the rest is kept, for the bundled lists and for any
refreshed copy (the filter is generic)."""

import re

from ike import darkfixes

OTHER_DR = re.compile(r"darkreader", re.I)


def test_engine_css_keeps_only_what_the_engine_can_use():
    css = ("a{color:${red} !important} .x[data-darkreader-inline-bgcolor]{color:red}"
           " b{background:var(--darkreader-bg--x)} c{background:var(--darkreader-neutral-background)}"
           " @media (max-width:5px){d{color:${blue}} e{--darkreader-x: 1}}"
           " f{background:linear-gradient(${red},blue)}")
    out = darkfixes.engine_css(css)
    assert "a {color:${red} !important}" in out
    assert "c {background:var(--darkreader-neutral-background)}" in out
    assert "@media (max-width:5px)" in out and "d {color:${blue}}" in out
    for gone in ("data-darkreader", "bg--x", "--darkreader-x", "linear-gradient"):
        assert gone not in out


def test_the_bundled_fixes_through_the_filter():
    total = kept = 0
    for fix in darkfixes.data()["fixes"]:
        css = fix.get("css") or ""
        if not css:
            continue
        out = darkfixes.engine_css(css)
        rest = darkfixes._ENGINE_VAR.sub("", out)
        assert not OTHER_DR.search(rest), fix["url"][:2]
        total += css.count("{")
        kept += out.count("{")
    assert total and kept >= 0.8 * total, (kept, total)
