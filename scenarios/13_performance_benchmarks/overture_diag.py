"""Scenario 13 -- run the Overture queries one per process, with diagnostics.

Two earlier Overture runs ended in an unexplained instance reboot during the
first full scan. This driver isolates each query in its own Python process and
prints to stdout (which the EC2 runner sends to the console log):
  * MemAvailable and the child's RSS every 10 s while a query runs
  * the child's exit code (a negative code means it was killed by a signal)
  * the last kernel messages after each query (OOM killer, hardware errors)

Each query writes its own result file: overture_<tag>_<query>.json.
Arguments other than --tag/--queries are passed through to overture.py.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import threading
import time

import psutil

import overture

HERE = pathlib.Path(__file__).resolve().parent


def mem_line(child: psutil.Process | None) -> str:
    vm = psutil.virtual_memory()
    rss = 0.0
    if child is not None:
        try:
            procs = [child] + child.children(recursive=True)
            rss = sum(p.memory_info().rss for p in procs) / 2**30
        except psutil.Error:
            pass
    return (f"available {vm.available / 2**30:.1f} GB of {vm.total / 2**30:.1f} GB, "
            f"query RSS {rss:.1f} GB, load {psutil.getloadavg()[0]:.1f}")


def kernel_tail(n: int = 15) -> str:
    try:
        out = subprocess.run(["dmesg", "--ctime"], capture_output=True, text=True,
                             timeout=10).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as e:
        return f"(dmesg unavailable: {e})"
    return "\n".join(out[-n:])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="diag")
    ap.add_argument("--queries", default="all")
    ap.add_argument("--interval", type=float, default=10.0)
    a, passthrough = ap.parse_known_args(argv)

    names = [q[0] for q in overture.QUERIES]
    if a.queries != "all":
        names = [n for n in names if n in set(a.queries.split(","))]

    failed = 0
    for name in names:
        print(f"DIAG {name} start: {mem_line(None)}", flush=True)
        cmd = [sys.executable, str(HERE / "overture.py"), "--queries", name,
               "--tag", f"{a.tag}_{name}", *passthrough]
        t0 = time.perf_counter()
        proc = subprocess.Popen(cmd)
        child = psutil.Process(proc.pid)
        stop = threading.Event()

        def sample() -> None:
            while not stop.wait(a.interval):
                print(f"DIAG {name} +{time.perf_counter() - t0:.0f}s: {mem_line(child)}",
                      flush=True)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        rc = proc.wait()
        stop.set()
        sampler.join()
        failed += rc != 0
        print(f"DIAG {name} exit {rc} after {time.perf_counter() - t0:.0f}s: "
              f"{mem_line(None)}", flush=True)
        print(f"DIAG {name} kernel log tail:\n{kernel_tail()}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
