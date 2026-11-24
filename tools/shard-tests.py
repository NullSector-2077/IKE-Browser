#!/usr/bin/env python3
"""The test suite split across parallel jobs, and the proof that every test ran once.

The owner's priority of 2026-11-24 (AUTOMAT block 1, step 1): one round of the
tests took about 40 minutes on Ubuntu ("Tests") and 70 to 90 on Arch Linux;
split across parallel jobs (shards) it takes a fraction, without losing a
single test or weakening any gate. Only pytest's own features: no new
dependency.

    shard-tests.py collect --out FILE
        the test ids pytest would run here (its own collection, through a
        plugin of this tool, into a file: never read from pytest's output),
        plus each test file skipped whole at collection (its id is the file)
        and each class skipped whole (its id), also listed in FILE.skipped;
    shard-tests.py plan --collected FILE --shards N [--shard K] [--timings FILE]
        which test files each shard runs: whole files, balanced by their
        recorded durations (TIMINGS), always the same answer for the same
        files, each file in exactly one shard;
    shard-tests.py run --kind KIND --shard K --shards N --out DIR [-- PYTEST ARGS]
        collects (DIR/collected.txt), plans, runs pytest on its own files only
        (junit into DIR/junit.xml) and records what it did (DIR/shard.json:
        the commit, the run and its attempt, the installed copy tested and the
        package's sha256 from IKE_PACKAGE_SHA256); exits with pytest's own code,
        but 0 for pytest's "no tests" when every file of the shard is skipped
        whole (their skips are still in its junit). A shard with no file runs
        nothing (pytest with no file would run the whole suite);
    shard-tests.py verify --kind KIND --shards N --dir DIR --sha SHA --run-id ID
                          [--collected FILE ...] [--package-sha256 SUM]
                          [--jobs-result RESULT] [--merged-junit OUT]
        the completeness gate: it fails when a shard is missing, ran another
        commit, another run or another part, failed or was cancelled (an
        installed shard: with no installed copy, or another package); when an
        independent collection is missing; when the shards did
        not collect the same tests (or not those of --collected, an independent
        collection); when any collected test did not run, ran twice, or a test
        ran that was not collected. Passed, failed and skipped all count as run:
        a skipped test is still reported as NOT VERIFIED by
        tools/test-categories.py, as before. With --merged-junit it writes
        every shard's results as one junit file (the one tools/test-categories.py
        and the maintenance ledger read), and only when every shard's is there;
    shard-tests.py timings --junit FILE [--junit FILE ...] [--timings FILE]
        records each test file's duration from junit files of real runs.

How a junit test case is matched to a collected id: pytest writes it as
(classname, name) by its own rule (`mangle_test_address` in _pytest/junitxml.py,
copied in junit_key below), so each collected id is turned into that pair and
the pairs are compared, never guessed backwards.

No network, no GitHub token, the standard library only (it runs in the gate
jobs with the runner's own Python).
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMINGS = ROOT / "tools" / "test-timings.json"
# a test file with no recorded duration (a new one) counts as this many seconds
DEFAULT_SECONDS = 20.0
KINDS = ("source", "installed")
SHARD_FILE = "shard.json"
JUNIT_FILE = "junit.xml"
COLLECTED_FILE = "collected.txt"

# The plugin the collection runs with. It opens the output file (named by an
# environment variable it removes at once) before any test module is imported,
# and writes the ids when the collection ends: a test module cannot add ids by
# printing them (the lesson of tests.yml's "No tests lost", audit of #65).
PLUGIN = '''\
import os
_out = []
_skipped = []
def pytest_configure(config):
    _out.append(open(os.environ.pop("IKE_SHARD_IDS_FILE"), "w", encoding="utf-8"))
def pytest_collectreport(report):
    if report.skipped and report.nodeid:
        _skipped.append(report.nodeid)
def pytest_collection_finish(session):
    _out[0].write("".join(item.nodeid + "\\n" for item in session.items))
    _out[0].write("".join("S " + nodeid + "\\n" for nodeid in _skipped))
    _out[0].close()
'''


class Problem(Exception):
    pass


# --- the ids and pytest's junit names ------------------------------------------------------------

_ILLEGAL_XML = re.compile("[^\u0009\u000a\u000d\u0020-\u007e\u0080-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _bin_xml_escape(text):
    """pytest's own escape of a junit name (_pytest/junitxml.py, bin_xml_escape)."""
    def repl(m):
        i = ord(m.group())
        return "#x%02X" % i if i <= 0xFF else "#x%04X" % i
    return _ILLEGAL_XML.sub(repl, text)


def junit_key(nodeid):
    """(classname, name) pytest's junit writes for a test id (mangle_test_address)."""
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), _bin_xml_escape(names[-1])


def file_of(nodeid):
    """The test file of an id; a whole skipped module's id is its file."""
    f = nodeid.split("::", 1)[0]
    if not f.endswith(".py"):
        raise Problem("cannot split by file: %r is not a test file (a skipped directory?)" % nodeid)
    return f


def _line(text):
    """One printed line: names come from the test files, and a line break in one would start a
    workflow command of GitHub's."""
    return re.sub(r"[\r\n\x00-\x1f]+", " ", str(text))


def read_ids(path):
    return [ln for ln in Path(path).read_text("utf-8").splitlines() if ln.strip()]


# --- the plan ------------------------------------------------------------------------------------

def load_timings(path=TIMINGS):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}, DEFAULT_SECONDS
    files = {str(k): float(v) for k, v in (data.get("files") or {}).items()
             if isinstance(v, (int, float)) and v >= 0}
    default = data.get("default")
    return files, float(default) if isinstance(default, (int, float)) and default > 0 else DEFAULT_SECONDS


def plan(ids, shards, timings=None, default=DEFAULT_SECONDS):
    """[files of shard 1, ..., files of shard N]: every file of the ids in exactly one shard, the
    longest first into the shard with the least so far (ties: the lower shard, then the name), so
    the same files and durations always give the same plan. Each shard's files in name order."""
    if not isinstance(shards, int) or shards < 1:
        raise Problem("the number of shards must be 1 or more, not %r" % (shards,))
    timings = timings or {}
    files = sorted({file_of(i) for i in ids})
    weight = {f: timings.get(f, default) for f in files}
    load = [0.0] * shards
    out = [[] for _ in range(shards)]
    for f in sorted(files, key=lambda f: (-weight[f], f)):
        k = min(range(shards), key=lambda i: (load[i], i))
        out[k].append(f)
        load[k] += weight[f]
    return [sorted(part) for part in out]


# --- collect and run -----------------------------------------------------------------------------

def collect(out, cwd=None, python=sys.executable, env=None):
    """The ids pytest would run in cwd (the repository's own settings), into the file out."""
    return collect_all(out, cwd, python, env)[0]


def collect_all(out, cwd=None, python=sys.executable, env=None):
    """(every id, the ids of what was skipped whole at collection: a module, a class), into the file
    out and, the skipped ones, into out + ".skipped"."""
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ike-shard-") as where:
        (Path(where) / "ike_shard_collect.py").write_text(PLUGIN, "utf-8")
        raw = Path(where) / "ids.txt"
        env = dict(os.environ if env is None else env)
        env["IKE_SHARD_IDS_FILE"] = str(raw)
        env["PYTHONPATH"] = where + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        run = subprocess.run([python, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=",
                              "-p", "no:cacheprovider", "-p", "ike_shard_collect"],
                             cwd=cwd, env=env, capture_output=True, text=True, check=False)
        if run.returncode != 0 or not raw.is_file():
            sys.stdout.write(run.stdout[-4000:] + run.stderr[-4000:])
            raise Problem("the collection failed (pytest exit %d)" % run.returncode)
        lines = read_ids(raw)
    skipped = [ln[2:] for ln in lines if ln.startswith("S ")]
    ids = [ln for ln in lines if not ln.startswith("S ")] + skipped
    if not ids:
        raise Problem("the collection found no test")
    out.write_text("".join(i + "\n" for i in ids), "utf-8")
    Path(str(out) + ".skipped").write_text("".join(i + "\n" for i in skipped), "utf-8")
    return ids, skipped


def run_shard(kind, shard, shards, out, pytest_args=(), timings_path=TIMINGS, cwd=None, python=sys.executable):
    """Collect, plan and run one shard's files; returns pytest's exit code (0 when it has no file)."""
    if kind not in KINDS:
        raise Problem("unknown kind %r" % kind)
    if not 1 <= shard <= shards:
        raise Problem("shard %d of %d does not exist" % (shard, shards))
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ids, skipped = collect_all(out / COLLECTED_FILE, cwd=cwd, python=python)
    timings, default = load_timings(timings_path)
    files = plan(ids, shards, timings, default)[shard - 1]
    junit = out / JUNIT_FILE
    print("Shard %d of %d (%s): %d of %d test files, %d tests collected in all"
          % (shard, shards, kind, len(files), len({file_of(i) for i in ids}), len(ids)), flush=True)
    for f in files:
        print("  " + f, flush=True)
    if files:
        # the files in name order, as pytest orders the whole directory
        code = subprocess.run([python, "-m", "pytest", *pytest_args, "--junitxml=%s" % junit, *files],
                              cwd=cwd, check=False).returncode
        mine = [i for i in ids if file_of(i) in set(files)]
        if code == 5 and mine and set(mine) <= set(skipped):
            # pytest's "no tests collected": every file of this shard is skipped whole at collection
            # (their skips are in the junit, and the gate counts them)
            print("every file of this shard is skipped whole: pytest's exit 5 is no failure", flush=True)
            code = 0
    else:
        junit.write_text('<?xml version="1.0" encoding="utf-8"?><testsuites></testsuites>\n', "utf-8")
        code = 0
    record = {"kind": kind, "shard": shard, "shards": shards, "sha": os.environ.get("GITHUB_SHA", ""),
              "run": os.environ.get("GITHUB_RUN_ID", ""), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
              "app": os.environ.get("IKE_TEST_APP", ""), "package_sha256": os.environ.get("IKE_PACKAGE_SHA256", ""),
              "files": files, "exit": code}
    (out / SHARD_FILE).write_text(json.dumps(record, indent=1) + "\n", "utf-8")
    return code


# --- the completeness gate -----------------------------------------------------------------------

def _shard_dirs(root, kind):
    """{shard number: [directories]} of every shard.json of this kind under root."""
    found = collections.defaultdict(list)
    for f in sorted(Path(root).rglob(SHARD_FILE)):
        try:
            rec = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            found["unreadable"].append(f.parent)
            continue
        if isinstance(rec, dict) and rec.get("kind") == kind:
            found[rec.get("shard")].append((f.parent, rec))
    return found


def _cases(junit):
    """[(classname, name, state)] of a junit file; state: passed, failed or skipped."""
    out = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            state = "failed"
        elif case.find("skipped") is not None:
            state = "skipped"
        else:
            state = "passed"
        out.append((case.get("classname") or "", case.get("name") or "", state))
    return out


def verify(kind, shards, root, collected=(), sha="", jobs_result="success", timings_path=TIMINGS,
           merged_junit=None, run_id="", package_sha256=""):
    """(problems, lines of the report). No problem: every shard there and green, of this commit and
    this run, every collected test run exactly once, nothing run that was not collected."""
    problems, report = [], []
    timings, default = load_timings(timings_path)
    if not sha:
        problems.append("no commit to check the shards against (--sha)")
    if not run_id:
        problems.append("no run to check the shards against (--run-id)")
    if jobs_result != "success":
        problems.append("the shard jobs ended with \"%s\", not success" % (jobs_result or "no result"))
    found = _shard_dirs(root, kind)
    for d in found.pop("unreadable", []):
        problems.append("an unreadable %s in %s" % (SHARD_FILE, d))
    shard_of = {}
    for k in range(1, shards + 1):
        entries = found.pop(k, [])
        if not entries:
            problems.append("shard %d of %d is missing (no results)" % (k, shards))
        elif len(entries) > 1:
            problems.append("shard %d of %d is there %d times" % (k, shards, len(entries)))
        else:
            shard_of[k] = entries[0]
    for k in found:
        problems.append("a shard %r that is not one of 1 to %d" % (k, shards))
    for k, (d, rec) in sorted(shard_of.items()):
        if rec.get("shards") != shards:
            problems.append("shard %d was split %r ways, not %d" % (k, rec.get("shards"), shards))
        if not rec.get("sha") or rec.get("sha") != sha:
            problems.append("shard %d ran commit %r, not %s" % (k, rec.get("sha"), sha))
        if not rec.get("run") or rec.get("run") != run_id:
            problems.append("shard %d is of run %r, not %s" % (k, rec.get("run"), run_id))
        if kind == "installed" and not rec.get("app"):
            problems.append("shard %d of the installed package tested no installed copy (IKE_TEST_APP)" % k)
        if kind == "source" and rec.get("app"):
            problems.append("shard %d of the sources tested an installed copy (%s)" % (k, rec.get("app")))
        if kind == "installed" and not rec.get("package_sha256"):
            problems.append("shard %d of the installed package recorded no package (sha256)" % k)
        if kind == "installed" and package_sha256 and rec.get("package_sha256") != package_sha256:
            problems.append("shard %d tested another package (sha256 %r, not %s)"
                            % (k, rec.get("package_sha256"), package_sha256))
        if rec.get("exit") != 0:
            problems.append("shard %d of %d: pytest ended with exit code %r (a test failed, or pytest stopped: "
                            "see that shard's job)" % (k, shards, rec.get("exit")))
    # the same tests everywhere: the independent collection(s) and every shard's own
    lists = []
    for p in collected:
        try:
            lists.append((str(p), read_ids(p)))
        except OSError:
            # (the job that collects stopped before it, a lint error say): the shards' own lists still
            # count, and the merge is still written; the gate fails
            problems.append("the independent collection is missing (%s)" % p)
    for k, (d, rec) in sorted(shard_of.items()):
        try:
            lists.append(("shard %d" % k, read_ids(d / COLLECTED_FILE)))
        except OSError:
            problems.append("shard %d recorded no collection" % k)
    if not lists:
        problems.append("no collection of the tests to compare with")
        return problems, report
    where, ids = lists[0]
    for other, theirs in lists[1:]:
        if sorted(theirs) != sorted(ids):
            gone, extra = sorted(set(ids) - set(theirs)), sorted(set(theirs) - set(ids))
            problems.append("%s collected other tests than %s (%d missing there, %d more there%s)" % (
                other, where, len(gone), len(extra), (": " + ", ".join((gone + extra)[:5])) if gone or extra else ""))
    if not ids:
        problems.append("the collection holds no test")
    dupes = [i for i, n in collections.Counter(ids).items() if n > 1]
    if dupes:
        problems.append("the collection holds %d id(s) twice: %s" % (len(dupes), ", ".join(dupes[:5])))
    try:
        parts = plan(ids, shards, timings, default)
    except Problem as e:
        problems.append(str(e))
        return problems, report
    keys = {}
    for i in ids:
        key = junit_key(i)
        if key in keys and keys[key] != i:
            problems.append("two tests share one junit name: %s and %s" % (keys[key], i))
        keys[key] = i
    ran = collections.Counter()
    states = collections.Counter()
    failed = []
    cases_of = {}
    for k, (d, rec) in sorted(shard_of.items()):
        if rec.get("files") != parts[k - 1]:
            problems.append("shard %d ran other files than its part of the plan" % k)
        mine = set(parts[k - 1])
        try:
            cases = _cases(d / JUNIT_FILE)
        except (OSError, ET.ParseError) as e:
            problems.append("shard %d's test results cannot be read (%s)" % (k, type(e).__name__))
            continue
        cases_of[k] = d / JUNIT_FILE
        for classname, name, state in cases:
            i = keys.get((classname, name))
            if i is None:
                problems.append("shard %d ran a test that was not collected: %s %s" % (k, classname, name))
                continue
            ran[i] += 1
            states[state] += 1
            if state == "failed":
                failed.append(i)
            if file_of(i) not in mine:
                problems.append("shard %d ran %s, a test of another shard" % (k, i))
    missing = [i for i in ids if not ran[i]]
    twice = [i for i in ids if ran[i] > 1]
    if missing:
        problems.append("%d collected test(s) did not run: %s" % (len(missing), ", ".join(missing[:10])))
    if twice:
        problems.append("%d test(s) ran more than once: %s" % (len(twice), ", ".join(twice[:10])))
    report.append("%s: %d tests collected, %d shards; run: %d passed, %d failed, %d skipped (not verified)"
                  % (kind, len(ids), shards, states["passed"], states["failed"], states["skipped"]))
    for k in range(1, shards + 1):
        part = parts[k - 1]
        report.append("  shard %d: %d files, about %d s by the recorded durations"
                      % (k, len(part), sum(timings.get(f, default) for f in part)))
    if failed:
        report.append("failed: " + ", ".join(failed[:20]) + (" and %d more" % (len(failed) - 20)
                                                             if len(failed) > 20 else ""))
    if merged_junit:
        if len(cases_of) == shards:
            merge_junit([cases_of[k] for k in range(1, shards + 1)], merged_junit)
        else:
            report.append("no merged results: not every shard's results could be read (not verified)")
    return problems, report


def merge_junit(paths, out):
    """Every test case of these junit files in one file, as pytest would have written one run."""
    suite = ET.Element("testsuite", name="pytest")
    counts = collections.Counter()
    for p in paths:
        root = ET.parse(p).getroot()
        for case in root.iter("testcase"):
            suite.append(case)
            counts["tests"] += 1
            for tag, key in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
                if case.find(tag) is not None:
                    counts[key] += 1
                    break
    for key in ("tests", "failures", "errors", "skipped"):
        suite.set(key, str(counts[key]))
    tree = ET.ElementTree(ET.Element("testsuites"))
    tree.getroot().append(suite)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    tree.write(out, encoding="utf-8", xml_declaration=True)


# --- the durations -------------------------------------------------------------------------------

def durations(paths):
    """{test file: seconds} summed over the junit files (each file's longest run wins)."""
    best = {}
    for p in paths:
        per = collections.Counter()
        for case in ET.parse(p).getroot().iter("testcase"):
            # the module is the first dotted part named test_*: tests.test_x[.TestClass], or the
            # name alone for a module skipped whole (classname "")
            parts = (case.get("classname") or case.get("name") or "").split(".")
            f = next(("/".join(parts[:n + 1]) + ".py" for n, part in enumerate(parts)
                      if part.startswith("test_")), None)
            if f:
                try:
                    per[f] += float(case.get("time") or 0)
                except ValueError:
                    pass
        for f, s in per.items():
            best[f] = max(best.get(f, 0.0), s)
    return best


def write_timings(found, path=TIMINGS):
    old, default = load_timings(path)
    files = dict(old)
    files.update({f: round(s, 1) for f, s in found.items()})
    values = sorted(files.values())
    if values:
        default = round(values[len(values) // 2], 1) or DEFAULT_SECONDS
    data = {"note": "seconds per test file, from junit files of real runs (tools/shard-tests.py timings); "
                    "the shards are balanced by them, a file not listed counts as \"default\"",
            "default": default, "files": dict(sorted(files.items()))}
    Path(path).write_text(json.dumps(data, indent=1) + "\n", "utf-8")
    return data


# --- the command line ----------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        extra = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--collected", required=True)
    p.add_argument("--shards", type=int, required=True)
    p.add_argument("--shard", type=int)
    p.add_argument("--timings", default=str(TIMINGS))
    r = sub.add_parser("run")
    r.add_argument("--kind", choices=KINDS, required=True)
    r.add_argument("--shard", type=int, required=True)
    r.add_argument("--shards", type=int, required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--timings", default=str(TIMINGS))
    v = sub.add_parser("verify")
    v.add_argument("--kind", choices=KINDS, required=True)
    v.add_argument("--shards", type=int, required=True)
    v.add_argument("--dir", required=True, help="where the shards' results were downloaded")
    v.add_argument("--collected", action="append", default=[], help="an independent collection (repeatable)")
    v.add_argument("--sha", required=True)
    v.add_argument("--run-id", required=True)
    v.add_argument("--package-sha256", default="", help="the package every installed shard must have tested")
    v.add_argument("--jobs-result", default="success", help="the shard jobs' result as GitHub gives it")
    v.add_argument("--timings", default=str(TIMINGS))
    v.add_argument("--merged-junit")
    t = sub.add_parser("timings")
    t.add_argument("--junit", action="append", required=True)
    t.add_argument("--timings", default=str(TIMINGS))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "collect":
            print("%d tests collected" % len(collect(a.out)))
        elif a.cmd == "plan":
            timings, default = load_timings(a.timings)
            parts = plan(read_ids(a.collected), a.shards, timings, default)
            if a.shard:
                if not 1 <= a.shard <= a.shards:
                    raise Problem("shard %d of %d does not exist" % (a.shard, a.shards))
                print("\n".join(parts[a.shard - 1]))
            else:
                print(json.dumps(parts, indent=1))
        elif a.cmd == "run":
            return run_shard(a.kind, a.shard, a.shards, a.out, extra, a.timings)
        elif a.cmd == "verify":
            problems, report = verify(a.kind, a.shards, a.dir, a.collected, a.sha, a.jobs_result, a.timings,
                                      a.merged_junit, a.run_id, a.package_sha256)
            print("\n".join(_line(r) for r in report))
            for why in problems:
                print("::error::%s" % _line(why))
            if problems:
                print("NOT COMPLETE: %d problem(s); the tests of this commit are not verified" % len(problems))
                return 1
            print("Complete: every collected test ran exactly once, in its own shard.")
        elif a.cmd == "timings":
            data = write_timings(durations(a.junit), a.timings)
            print("%d test files recorded, default %s s" % (len(data["files"]), data["default"]))
    except Problem as e:
        print("::error::%s" % _line(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
