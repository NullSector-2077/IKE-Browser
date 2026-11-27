"""Compare CPU time and sampled process-tree PSS on Linux.

Requires psutil. Each mode runs in fresh Qt processes, in alternating order:

    python3 tests/dark_engine/resources.py OUT_DIR --runs 3 --bench 5

The CPU total includes time observed in extant processes, so a child that
terminates between samples may be missed. PSS apportions shared pages among
processes. GPU hardware usage is outside these metrics.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

import psutil


def sample(process, cpu):
    pss = 0
    complete = True
    try:
        processes = [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return None
    for child in processes:
        try:
            with child.oneshot():
                ident = child.pid, child.create_time()
                times = child.cpu_times()
                cpu[ident] = max(cpu.get(ident, 0), times.user + times.system)
                pss += child.memory_full_info().pss
        except psutil.NoSuchProcess:
            complete = False
        except psutil.AccessDenied:
            complete = False
    return pss if complete else None


def run(out, mode, bench):
    out.mkdir(parents=True, exist_ok=True)
    renderer = Path(__file__).with_name("render.py")
    cpu = {}
    peak_pss = 0
    with (out / "render.log").open("w") as log:
        with subprocess.Popen([sys.executable, str(renderer), str(out), "--modes", mode,
                               "--bench-only", "--bench", str(bench)],
                              stdout=log, stderr=subprocess.STDOUT) as child:
            process = psutil.Process(child.pid)
            while child.poll() is None:
                pss = sample(process, cpu)
                if pss is not None:
                    peak_pss = max(peak_pss, pss)
                time.sleep(0.1)
        if child.returncode:
            raise RuntimeError(f"{mode} failed. See {out / 'render.log'}.")
    results = json.loads((out / "results.json").read_text())
    durations = results["bench"][mode]
    if len(durations) != bench or not peak_pss:
        raise RuntimeError(f"Incomplete resource measurement for {mode}.")
    return {"bench_ms": durations, "observed_cpu_seconds": round(sum(cpu.values()), 2),
            "peak_pss_mib": round(peak_pss / (1024 * 1024), 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--bench", type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1 or args.bench < 1:
        parser.error("--runs and --bench must be positive")
    trials = {"dr": [], "proto": []}
    for n in range(args.runs):
        for mode in (("proto", "dr") if n % 2 else ("dr", "proto")):
            trial = run(args.out / f"{n + 1}-{mode}", mode, args.bench)
            trials[mode].append(trial)
            print(f"{n + 1} {mode} {trial}", flush=True)
    summary = {mode: {"bench_ms": median(t for row in rows for t in row["bench_ms"]),
                      "observed_cpu_seconds": median(row["observed_cpu_seconds"] for row in rows),
                      "peak_pss_mib": median(row["peak_pss_mib"] for row in rows)}
               for mode, rows in trials.items()}
    (args.out / "resources.json").write_text(json.dumps({"summary": summary, "trials": trials}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
