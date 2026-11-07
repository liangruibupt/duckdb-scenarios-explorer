"""Scenario 13 -- TPC-H scale benchmark (SF1 / SF10 / SF100).

Generates TPC-H data with DuckDB's built-in `tpch` extension, then runs the 22
standard queries and records, per query:
  * wall time
  * peak process RSS (sampled)
  * peak buffer-manager memory and peak spill, from `duckdb_memory()`
  * peak size of the temp (spill) directory on disk

Two sources:
  --source native   query the .duckdb file the data was generated into (default)
  --source parquet  export every table to Parquet once, then query Parquet views
                    in a fresh in-memory database (the "query files" pattern)

Data generation is chunked (`dbgen(sf, children, step)`) so SF100 fits in a
small machine's RAM. Results go to results/sf<SF>_<source>.json and .md.

Usage:
  python bench.py --sf 1
  python bench.py --sf 10 --memory-limit 10GB
  python bench.py --sf 100 --memory-limit 10GB --threads 4 --queries 1,3,6,9,13,18,21
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import threading
import time

import duckdb

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"
TABLES = ["customer", "lineitem", "nation", "orders",
          "part", "partsupp", "region", "supplier"]
# SF values that tpch_answers() carries reference results for.
ANSWER_SFS = {0.01, 0.1, 1}


def sf_label(sf: float) -> str:
    return str(int(sf)) if float(sf).is_integer() else str(sf).replace(".", "_")


def dir_bytes(path: pathlib.Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass  # spill files come and go while we walk
    return total


def configure(con: duckdb.DuckDBPyConnection, memory_limit: str | None,
              threads: int | None, temp_dir: pathlib.Path,
              max_temp: str | None) -> None:
    con.execute("INSTALL tpch; LOAD tpch")
    if memory_limit:
        con.execute(f"SET memory_limit = '{memory_limit}'")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{temp_dir.as_posix()}'")
    if max_temp:
        con.execute(f"SET max_temp_directory_size = '{max_temp}'")
    # The benchmark does not need result order to match insertion order.
    con.execute("SET preserve_insertion_order = false")


def generate(db_path: pathlib.Path, sf: float, children: int, **cfg) -> float:
    """Generate TPC-H at `sf` into db_path in `children` chunks. Returns seconds."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    configure(con, **cfg)
    done = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'lineitem'"
    ).fetchone()[0]
    if done:
        con.close()
        return 0.0
    t0 = time.perf_counter()
    if children <= 1:
        con.execute(f"CALL dbgen(sf = {sf})")
    else:
        for step in range(children):
            con.execute(f"CALL dbgen(sf = {sf}, children = {children}, step = {step})")
            print(f"  dbgen step {step + 1}/{children} "
                  f"({time.perf_counter() - t0:,.0f}s)", flush=True)
    con.execute("CHECKPOINT")
    con.close()
    return time.perf_counter() - t0


def export_parquet(db_path: pathlib.Path, out_dir: pathlib.Path, **cfg) -> float:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    configure(con, **cfg)
    t0 = time.perf_counter()
    for t in TABLES:
        target = out_dir / f"{t}.parquet"
        if not target.exists():
            con.execute(f"COPY {t} TO '{target.as_posix()}' "
                        "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880)")
    con.close()
    return time.perf_counter() - t0


class Sampler:
    """Background sampler for peak RSS, buffer memory, spill and temp-dir size."""

    def __init__(self, con: duckdb.DuckDBPyConnection, temp_dir: pathlib.Path,
                 interval: float = 0.1):
        import psutil
        self.proc = psutil.Process()
        self.cur = con.cursor()  # separate cursor; safe to query while a query runs
        self.temp_dir = temp_dir
        self.interval = interval
        self._stop = threading.Event()
        self.peak_rss = self.peak_mem = self.peak_spill = self.peak_tmpdir = 0

    def _sample(self) -> None:
        self.peak_rss = max(self.peak_rss, self.proc.memory_info().rss)
        try:
            mem, spill = self.cur.execute(
                "SELECT coalesce(sum(memory_usage_bytes), 0), "
                "coalesce(sum(temporary_storage_bytes), 0) FROM duckdb_memory()"
            ).fetchone()
            self.peak_mem = max(self.peak_mem, int(mem))
            self.peak_spill = max(self.peak_spill, int(spill))
        except duckdb.Error:
            pass
        self.peak_tmpdir = max(self.peak_tmpdir, dir_bytes(self.temp_dir))

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def __enter__(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self._sample()
        self.cur.close()


def check_answer(con: duckdb.DuckDBPyConnection, q: int, sf: float,
                 rows: list[tuple]) -> bool | None:
    """Compare against tpch_answers() when the SF has reference answers."""
    if sf not in ANSWER_SFS:
        return None
    ans = con.execute(
        "SELECT answer FROM tpch_answers() WHERE query_nr = ? AND scale_factor = ?",
        [q, sf]).fetchone()
    if not ans:
        return None
    # Header line first; a NULL-only row renders as an empty line, so drop only
    # the single trailing newline instead of stripping all whitespace.
    lines = ans[0].split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return len(lines) - 1 == len(rows)


def run_queries(con: duckdb.DuckDBPyConnection, sf: float, queries: list[int],
                temp_dir: pathlib.Path) -> list[dict]:
    out = []
    for q in queries:
        sql = con.execute(
            "SELECT query FROM tpch_queries() WHERE query_nr = ?", [q]).fetchone()[0]
        err = None
        rows: list[tuple] = []
        with Sampler(con, temp_dir) as s:
            t0 = time.perf_counter()
            try:
                rows = con.execute(sql).fetchall()
            except duckdb.Error as e:  # e.g. out-of-memory or temp dir full
                err = f"{type(e).__name__}: {e}".splitlines()[0][:300]
            secs = time.perf_counter() - t0
        rec = {
            "query": q,
            "seconds": round(secs, 3),
            "rows": len(rows),
            "peak_rss_gb": round(s.peak_rss / 2**30, 2),
            "peak_buffer_gb": round(s.peak_mem / 2**30, 2),
            "peak_spill_gb": round(max(s.peak_spill, s.peak_tmpdir) / 2**30, 2),
            "ok": err is None,
            "answer_rowcount_match": None if err else check_answer(con, q, sf, rows),
            "error": err,
        }
        out.append(rec)
        status = "ok" if err is None else "FAILED"
        print(f"  Q{q:02d} {secs:8.2f}s  rss {rec['peak_rss_gb']:5.2f} GB  "
              f"spill {rec['peak_spill_gb']:5.2f} GB  {status}", flush=True)
    return out


def open_for_queries(db_path: pathlib.Path, source: str,
                     parquet_dir: pathlib.Path, **cfg) -> duckdb.DuckDBPyConnection:
    if source == "native":
        con = duckdb.connect(str(db_path), read_only=True)
        configure(con, **cfg)
        return con
    con = duckdb.connect()  # in-memory: everything is read from Parquet files
    configure(con, **cfg)
    for t in TABLES:
        con.execute(f"CREATE VIEW {t} AS "
                    f"SELECT * FROM read_parquet('{(parquet_dir / f'{t}.parquet').as_posix()}')")
    return con


def machine_info() -> dict:
    import psutil
    return {
        "cpus": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "duckdb": duckdb.__version__,
        # set by the EC2 runner; empty on other machines
        "instance_type": os.environ.get("BENCH_INSTANCE_TYPE", ""),
    }


def to_markdown(r: dict) -> str:
    m, c = r["machine"], r["config"]
    gs = r["generate_seconds"]
    gen = f"{gs:,.0f} s" if gs else "reused an existing file"
    lines = [
        f"# TPC-H SF{r['sf']} · source = {r['source']}",
        "",
        f"- Machine: {m.get('instance_type') or 'local'}: {m['cpus']} vCPU, {m['ram_gb']} GB RAM, "
        f"{m['machine']}, DuckDB {m['duckdb']}",
        f"- Settings: memory_limit={c['memory_limit'] or 'default (80% RAM)'}, "
        f"threads={c['threads'] or 'default'}",
        f"- Data: generation {gen}; database file "
        f"{r['db_file_gb']} GB; Parquet {r.get('parquet_gb', '-')} GB",
        f"- Total query time: {r['total_seconds']:,.1f} s "
        f"({r['queries_ok']}/{len(r['queries'])} queries succeeded)",
        "",
        "| Query | Seconds | Peak RSS (GB) | Peak buffer (GB) | Peak spill (GB) | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for q in r["queries"]:
        status = "ok" if q["ok"] else f"failed: {q['error']}"
        lines.append(f"| Q{q['query']:02d} | {q['seconds']:.2f} | {q['peak_rss_gb']:.2f} | "
                     f"{q['peak_buffer_gb']:.2f} | {q['peak_spill_gb']:.2f} | {status} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sf", type=float, default=1.0)
    ap.add_argument("--source", choices=["native", "parquet"], default="native")
    ap.add_argument("--queries", default="all", help="'all' or e.g. 1,3,6")
    ap.add_argument("--memory-limit", default=None, help="e.g. 10GB")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--max-temp", default=None, help="cap spill, e.g. 30GB")
    ap.add_argument("--children", type=int, default=None,
                    help="dbgen chunks (default: 1 below SF10, else SF/5)")
    ap.add_argument("--data-dir", default=str(DATA))
    ap.add_argument("--results-dir", default=str(RESULTS))
    ap.add_argument("--tag", default="", help="suffix for result file names, e.g. mem16g")
    a = ap.parse_args(argv)

    data_dir = pathlib.Path(a.data_dir)
    label = sf_label(a.sf)
    db_path = data_dir / f"tpch_sf{label}.duckdb"
    parquet_dir = data_dir / f"tpch_sf{label}_parquet"
    temp_dir = data_dir / f"tmp_sf{label}"
    cfg = dict(memory_limit=a.memory_limit, threads=a.threads,
               temp_dir=temp_dir, max_temp=a.max_temp)
    children = a.children or (1 if a.sf < 10 else max(2, int(a.sf // 5)))
    queries = list(range(1, 23)) if a.queries == "all" else \
        [int(x) for x in a.queries.split(",")]

    print(f"TPC-H SF{a.sf}: generating into {db_path} ({children} chunk(s))", flush=True)
    gen_s = generate(db_path, a.sf, children, **cfg)
    result = {
        "sf": a.sf, "source": a.source, "tag": a.tag, "machine": machine_info(),
        "config": {"memory_limit": a.memory_limit, "threads": a.threads,
                   "max_temp": a.max_temp, "children": children},
        "generate_seconds": round(gen_s, 1),
        "db_file_gb": round(db_path.stat().st_size / 2**30, 2),
    }
    if a.source == "parquet":
        result["export_seconds"] = round(export_parquet(db_path, parquet_dir, **cfg), 1)
        result["parquet_gb"] = round(dir_bytes(parquet_dir) / 2**30, 2)

    con = open_for_queries(db_path, a.source, parquet_dir, **cfg)
    print(f"Running {len(queries)} queries (source={a.source})", flush=True)
    result["queries"] = run_queries(con, a.sf, queries, temp_dir)
    con.close()
    result["total_seconds"] = round(sum(q["seconds"] for q in result["queries"]), 1)
    result["queries_ok"] = sum(q["ok"] for q in result["queries"])

    out_dir = pathlib.Path(a.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"sf{label}_{a.source}{'_' + a.tag if a.tag else ''}"
    # Build names by concatenation: a tag such as "m8g.xlarge" contains a dot,
    # which Path.with_suffix would treat as an extension.
    pathlib.Path(f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n")
    pathlib.Path(f"{stem}.md").write_text(to_markdown(result))
    print(f"Wrote {stem}.json / .md  total {result['total_seconds']:,.1f}s", flush=True)
    return result


if __name__ == "__main__":
    main()
