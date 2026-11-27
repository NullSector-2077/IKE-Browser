#!/bin/sh
# Which part of the Dark Engine keeps a page busy: copies of the engine with one
# part changed (tests/dark_engine/variants.py), each next to the page without
# dark mode ("off"). Read-only, as owner-check.sh (a private profile).
#   sh tests/dark_engine/busy-check.sh ADDRESS [--click "I'm Over 18"] [--modes off,protolog,...]
# Modes: proto (as it is), protonopic, protonolook, protolog (every picture
# written to run.log), protonosvg, protonofrag.
here=$(cd "$(dirname "$0")" && pwd)
url="$1"; shift
[ -n "$url" ] || { echo "usage: $0 ADDRESS [--click TEXT] [--modes ...]"; exit 2; }
modes="off,protolog,protonosvg,protonofrag"
case "$1" in --modes) modes="$2"; shift 2;; esac
case "$3" in --modes) modes="$4"; set -- "$1" "$2";; esac
tmp=$(mktemp -d)
python3 "$here/variants.py" "$tmp" || exit 1
out="$HOME/ike-dark-busy-$(date +%F)"
rm -rf "$out"
DE_JS_protonopic="$tmp/nopic.js" DE_JS_protonolook="$tmp/nolook.js" DE_JS_protolog="$tmp/log.js" \
DE_JS_protonosvg="$tmp/nosvg.js" DE_JS_protonofrag="$tmp/nofrag.js" \
    sh "$here/owner-check.sh" --modes "$modes" --url "$url" "$@" "$out"
echo
echo "== what happened (send this):"
grep -E "forced|clicked|shot|still|answered|busy|error|Trace" "$out/run.log"
if grep -q "\[ike-de\]" "$out/run.log"; then
    echo "== the last pictures before it stopped:"
    grep "\[ike-de\]" "$out/run.log" | tail -15
    echo "== the slowest:"
    grep "drawn in" "$out/run.log" | sort -t' ' -k5 -n | tail -5
    echo "pictures asked: $(grep -c 'ike-de. asked' "$out/run.log")"
    echo "== who asks again:"
    grep "ike-de. stack" "$out/run.log" | head -6
fi
rm -rf "$tmp"
