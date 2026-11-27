#!/bin/sh
# Which part of the Dark Engine keeps a page busy: the same page with the engine
# as it is ("proto"), without its look at whether the page is dark already
# ("nolook") and without its analysis of pictures ("nopic"), each next to the page
# without dark mode ("off"). Read-only, as owner-check.sh (a private profile).
#   sh tests/dark_engine/busy-check.sh ADDRESS [--click "I'm Over 18"]
here=$(cd "$(dirname "$0")" && pwd)
url="$1"; shift
[ -n "$url" ] || { echo "usage: $0 ADDRESS [--click TEXT]"; exit 2; }
tmp=$(mktemp -d)
js="$here/../../ike/darkengine.js"
sed 's/^  function looksDarkNow() {$/  function looksDarkNow() { return false;/' "$js" > "$tmp/nolook.js"
sed "s/^  function picture(url, done) {\$/  function picture(url, done) { return { state: 'keep', data: null, waiting: [] };/" "$js" > "$tmp/nopic.js"
grep -q "looksDarkNow() { return false;" "$tmp/nolook.js" && grep -q "picture(url, done) { return" "$tmp/nopic.js" ||
    { echo "the engine changed: this check needs updating"; exit 1; }
out="$HOME/ike-dark-busy-$(date +%F)"
rm -rf "$out"
DE_JS_protonolook="$tmp/nolook.js" DE_JS_protonopic="$tmp/nopic.js" \
    sh "$here/owner-check.sh" --modes off,proto,protonolook,protonopic --url "$url" "$@" "$out"
echo
echo "== what happened (send this):"
grep -E "clicked|shot|still|answered|busy|error|Trace" "$out/run.log"
rm -rf "$tmp"
