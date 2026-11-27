#!/usr/bin/env python3
"""AUTOMAT's playbook: what a failure of an updated component usually means in I.K.E., where its fix goes and
how to write it so that the checks accept it (no AI here; written and kept by Claude).

The owner (2026-11-27): the AIs must be able to fix every problem of I.K.E., with their work made simple by
someone who knows how I.K.E. works and what its updatable components can break. On PR #111 the free models
were given only the engine's error ("network filter error: csp with content type"): they guessed, put a new
function between two methods of a class (which took a method out of it) and added code nothing called; the
static guard refused it, rightly, and nothing reached the users. This file gives them what they lacked.

tools/autofix-context.py adds the matching entries to .autofix/context.md, which Antigravity and every reserve
read, and puts the entry's files first among the files involved. Each entry:

    id        a name, used in the tests
    signs     regular expressions; the entry matches when one is found in the failure (case ignored)
    meaning   what the failure means in I.K.E.
    where     the files (and function) where the fix belongs, existing files of the repository
    how       how to write the fix so that it passes the checks (tools/fix-guard.py, the tests)
    never     what must not be done (never weakens blocking or protection, never tier B)

GENERAL holds the rules every fix follows; it is added whenever an entry matches. An entry whose fix is not an
AI's (tier B, the owner's decisions) says so in "how": the AI answers "fixable": false with that reason, so the
attempt is recorded and the right person is told, instead of a guess.

    automat-playbook.py match FAILURE.md      (prints the advice, for a person)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_ENTRIES = 3

GENERAL = (
    "Only ADD statements: never change, move or delete an existing line (the static guard, tools/fix-guard.py, "
    "refuses it). To make an existing function do more, add a new statement inside it (for example a new line "
    "`text = _new_step(text)` just before its final `return`), and put the new helper function at module level, "
    "outside every class, after the last line of the class or function above it. A `def` placed between two "
    "methods of a class takes the methods after it out of the class (PR #111).",
    "Every new function must be called by the code: a helper nothing calls fixes nothing.",
    "Keep both the old and the new version of a component working when you can (a fallback), so the fix does not "
    "depend on which version a user has.",
    "Never weaken ad blocking, the fingerprint protection or any security check, never touch YouTube's ad "
    "blocking, the tests, the workflows or tools/: if the fix needs one of those, answer \"fixable\": false and "
    "say which file and why.",
)

PLAYBOOK = (
    {
        "id": "adblock-csp-with-content-type",
        "signs": (r"csp with content type", r"CspWithContentType"),
        "meaning": "The AdBlock engine (adblock-rust) refuses a network rule that has `csp=` together with a "
                   "content-type option such as `$doc`/`$document`. I.K.E.'s adapter may not drop the option "
                   "(tests/test_lists_recorded.py refuses a rule rewritten without one of its options), and "
                   "I.K.E. applies no `$csp` rule at all: Qt WebEngine cannot add a response header.",
        "where": (),
        "how": "Not fixable in I.K.E.'s adapter: answer \"fixable\": false with \"an engine limit: adblock-rust "
               "refuses csp= with a content type, and I.K.E. applies no $csp rule\". tools/filter-lists.py "
               "ENGINE_LIMITS no longer gives this finding to an AI.",
        "never": "Never drop the `$doc` option or the rule, never add code that nothing calls to look like a fix.",
    },
    {
        "id": "adblock-unrecognised-option",
        "signs": (r"network filter error: unrecognised option", r"UnrecognisedOption"),
        "meaning": "A rule of the filter lists uses an option the bundled AdBlock engine does not know (often a "
                   "newer uBlock Origin alias of an option it does know). The engine drops the whole rule.",
        "where": ("ike/blocker.py",),
        "how": "When the option is an alias of one the engine knows (uBlock Origin's documented aliases: `doc` = "
               "`document`, `css` = `stylesheet`, `xhr` = `xmlhttprequest`, `frame` = `subdocument`, `1p` = "
               "`first-party`, `3p` = `third-party`, `ehide` = `elemhide`, `ghide` = `generichide`, `shide` = "
               "`specifichide`), add a rewrite to that name in a new module-level function called from "
               "`sanitize` (a new statement before its final `return`). When it has no equivalent, answer "
               "\"fixable\": false: the engine itself must learn it (an engine update).",
        "never": "Never rewrite a blocking rule into a weaker one, never drop the option silently.",
    },
    {
        "id": "scriptlet-unknown",
        "signs": (r"unknown scriptlet", r"scriptlet [^\n]{0,80}not (?:known|in the library)"),
        "meaning": "A `+js(...)` rule names a scriptlet the bundled uBlock Origin library does not have by that "
                   "name: usually a new alias of an existing scriptlet, or a scriptlet newer than the library.",
        "where": ("ike/scriptlets.py",),
        "how": "In ike/scriptlets.py, `Library.resolve` maps a rule's token to the library's name through the "
               "aliases the library lists. If the new name is an alias uBlock Origin documents for an existing "
               "scriptlet, add it with a new statement (inside a method, or a module-level mapping used by a new "
               "statement in `resolve`), never by changing the existing lines. If the scriptlet is new upstream, "
               "answer \"fixable\": false: the library is rebuilt by the builder (tools/build-ubo-scriptlets.mjs).",
        "never": "Never touch YouTube's scriptlets or their rules (the owner's decision).",
    },
    {
        "id": "builder-anchor",
        "signs": (r"builder refused", r"anchor [^\n]{0,60}(?:not found|found \d+ times|more than once)"),
        "meaning": "A new upstream version of Dark Reader or uBlock Origin moved the code one of I.K.E.'s existing "
                   "patches is anchored to.",
        "where": ("tools/build-darkreader.py", "tools/build-ubo-scriptlets.mjs"),
        "how": "Only on the builder's branch, and only the anchor texts: find in the new upstream code the one "
               "place equivalent to the old anchor and give it as the new anchor; the replacement texts stay "
               "byte-identical, no patch is added or removed (tools/builder-anchor.py checks it).",
        "never": "Never change a replacement, never change upstream code.",
    },
    {
        "id": "qt-api-renamed",
        "signs": (r"AttributeError: [^\n]*'(?:Q\w+|PyQt6[\w.]*)'[^\n]* has no attribute",
                  r"cannot import name '\w+' from 'PyQt6",
                  r"module 'PyQt6\.\w+' has no attribute",
                  r"TypeError: [^\n]*Q\w+\.\w+\([^\n]*\): (?:argument|too many|not enough)"),
        "meaning": "A Qt or PyQt update renamed, moved or changed the signature of something I.K.E. uses (Qt 6.8 "
                   "replaced the permission API; enums move between classes). The browser then breaks where "
                   "that module runs.",
        "where": (),
        "how": "Fix the I.K.E. module the traceback names (an ordinary module of ike/). Keep both versions "
               "working: read the new name with a fallback to the old one, e.g. a new module-level line "
               "`_NEW = getattr(QtClass, \"NewName\", None) or getattr(QtClass, \"OldName\")` and use it in a new "
               "statement. Other uses of the same name in the code are listed below the failure: fix them the "
               "same way. Qt's documentation names the replacement of a removed API.",
        "never": "Never remove the feature that used it; ike/app.py, ike/updater.py and ike_boot.py are tier B "
                 "(answer \"fixable\": false if the fix is there).",
    },
    {
        "id": "python-stdlib-removed",
        "signs": (r"ModuleNotFoundError: No module named '(?:imghdr|cgi|cgitb|crypt|telnetlib|nntplib|pipes|"
                  r"sndhdr|spwd|sunau|uu|xdrlib|aifc|audioop|chunk|mailcap|msilib|nis|ossaudiodev|asynchat|"
                  r"asyncore|smtpd|distutils)'",
                  r"DeprecationWarning: [^\n]* (?:is deprecated and slated for removal|will be removed)"),
        "meaning": "A new Python on Arch removed (or will remove) a standard-library module or function I.K.E. "
                   "uses.",
        "where": (),
        "how": "In the I.K.E. module the traceback names, use the replacement the Python documentation gives "
               "(e.g. `imghdr` -> read the file's first bytes; `cgi.parse_header` -> `email.message.Message`; "
               "`pipes.quote` -> `shlex.quote`), imported in a new statement, with the old import kept only "
               "inside a `try` the new code does not need.",
        "never": "Never add a dependency that Arch does not install with I.K.E.",
    },
    {
        "id": "rust-wrapper-api",
        "signs": (r"error\[E0(?:425|432|433|599|061|308|277)\][^\n]*", r"ike-adblock/src/lib\.rs:\d+"),
        "meaning": "An update of the adblock crate or of pyo3 changed an API the engine wrapper "
                   "(ike-adblock/src/lib.rs) uses: a renamed function, a moved type, a new argument.",
        "where": ("ike-adblock/src/lib.rs",),
        "how": "Change only the wrapper, at the line the compiler names, to the crate's new API (the compiler's "
               "own `help:` lines and the crate's changelog in the failure give the new name). Keep every "
               "function the Python side calls (Engine, FilterSet, check_network_urls, get_csp_directives, "
               "url_cosmetic_resources, hidden_class_id_selectors, add_resource, serialize, deserialize) with "
               "the same name and arguments.",
        "never": "Never remove a check the wrapper makes (the `guarded` calls), never change the crate versions.",
    },
    {
        "id": "nothing-gets-worse-fingerprint",
        "signs": (r"Nothing gets worse", r"things worse than on main"),
        "meaning": "The differential check measured the candidate worse than main. When the change does not "
                   "touch what got worse (e.g. fingerprint rows on a Dark Reader update), the branch is usually "
                   "behind main and measures main's older protection: that is not for an AI.",
        "where": (),
        "how": "If the rows that got worse belong to a file this change does not touch, answer \"fixable\": "
               "false with \"the branch is behind main: it needs main merged in, not a fix\". Otherwise make "
               "the protection at least as strong as main's again.",
        "never": "Never edit the allowlist or the measures; ike/resources/fingerprint.js changes need three "
                 "reviewers and only stricter rows.",
    },
    {
        "id": "tier-b-engine-switches",
        "signs": (r"File \"[^\"]*ike/app\.py\", line \d+, in \w+\n(?!\s*File)", r"ike_boot\.py:\d+",
                  r"ike/updater\.py:\d+", r"\.github/workflows/[\w.-]+\.yml"),
        "meaning": "The failure is in a file only Claude or a person changes (tier B: the engine's switches, the "
                   "start, the update channel, the workflows).",
        "where": (),
        "how": "If the fix is in one of these files, answer \"fixable\": false and name the file and the change "
               "it needs: the attempt is recorded and Claude is told. If the cause is in an ordinary module "
               "the traceback also names, fix it there.",
        "never": "Never change a tier-B file, not even one line, not even to add a fallback.",
    },
)


def match(failure):
    """The entries whose signs are in the failure text, at most MAX_ENTRIES, in the playbook's order."""
    text = str(failure or "")
    found = []
    for entry in PLAYBOOK:
        if any(re.search(sign, text, re.I) for sign in entry["signs"]):
            found.append(entry)
    return found[:MAX_ENTRIES]


def advice(failure):
    """(markdown, files) for .autofix/context.md: what the failure usually means, where and how to fix it."""
    found = match(failure)
    if not found:
        return "", []
    out = ["# What this failure usually means in I.K.E. (AUTOMAT's playbook)", "",
           "Written by the people who know I.K.E.; follow it unless the code shows otherwise.", ""]
    files = []
    for entry in found:
        out += ["## %s" % entry["id"], "", "- **Meaning**: %s" % entry["meaning"]]
        if entry["where"]:
            out.append("- **Where**: %s" % ", ".join("`%s`" % w for w in entry["where"]))
            files += [w for w in entry["where"] if w not in files]
        out += ["- **How**: %s" % entry["how"], "- **Never**: %s" % entry["never"], ""]
    out += ["## Rules of every fix", ""] + ["- %s" % rule for rule in GENERAL] + [""]
    return "\n".join(out) + "\n", files


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "match":
        print(__doc__.split("\n\n")[-1].strip(), file=sys.stderr)
        return 2
    text, _files = advice(Path(argv[1]).read_text("utf-8", errors="replace"))
    print(text or "No entry of the playbook matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
