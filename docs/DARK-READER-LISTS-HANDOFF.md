# Dark Reader list updates

The experimental branch refreshes compatibility data in the browser.
The installed engine and its bundled fallback stay tied to the signed
I.K.E. package. The daily list check runs in the background when page dark
mode is in use. I.K.E. reads the public Dark Reader head on GitHub and
fetches the three configuration files at that exact commit. The requests
use the browser's DNS policy and carry no browsing URLs or cookies.

Each process uses a single list snapshot. Validation runs before the
cache is replaced atomically, and a new process loads the staged cache.
If validation fails, the previous cache stays available. If there is no
usable cache, I.K.E. uses its bundled list. Remote CSS that could create
external requests falls back to the matching bundled CSS where available.
Regular-expression URL patterns must already be present in the bundle.
The runtime update downloads data over HTTPS and never installs engine
JavaScript. Bundled fallback quality still matters for offline use.

## Workflow changes for Claude

1. Separate Dark Reader **engine releases** from **list head movement** in
   `tools/check-components.py`. Its `check_darkreader` comparison and
   `apply_darkreader` path currently track both. A list hash or commit change
   by itself should be informational. It should produce no release candidate,
   Git commit against the bundled snapshot, release package, or CI run.
2. Check the dependency mapping in `components.json` and the candidate
   plan in `tools/update-candidates.py`. Retain Dark Reader engine and proxy
   verification. Do not create an `automation/update/darkreader` candidate
   solely because list data moved.
3. Keep `.github/workflows/daily-check.yml` and
   `.github/workflows/daily-maintenance.yml` focused on actionable engine
   changes. Verify the candidate output consumed by
   `.github/workflows/automerge.yml` and `.github/workflows/release-ready.yml`
   contains no list-only release trigger.
4. Refresh the bundled fallback when packaging a new Dark Reader engine
   or intentionally refreshing bundled data in an I.K.E. release.
   `tools/build-darkreader.py` assembles it, including the engine and proxy.
   `tools/make-release.py` carries the resource in the signed payload.
5. Exercise two cases locally before changing workflow behavior. A newer
   list commit with the same engine should produce no candidate. A newer
   engine should still produce a candidate that is tested and packaged.
   Keep checks of the installed fallback and the application-side cache
   in normal regression suites.

The workflow and release-automation changes are for Claude's separate
work. This branch's runtime implementation lives in `ike/darklists.py`,
`ike/darkfixes.py` and the existing `IkeApp.check_updates` timer.

## Verification

The live fetch staged upstream revision
`2bd262585f149693d23779283b69013da513f2ce` in a disposable cache. The
loader validated 2,953 fixes, 1,315 dark-site patterns and 232 detector
hints. The regression suite checks single-commit inputs, fallback for
request-capable CSS, stale and invalid responses, the daily interval and
the snapshot used by both engines across a restart.
