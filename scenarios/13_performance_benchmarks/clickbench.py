"""Scenario 13 -- ClickBench (web-analytics benchmark, 100M rows, 14.8 GB Parquet).

Downloads the public `hits.parquet`, then runs ClickBench's 43 DuckDB queries
three times each (the ClickBench convention: first run is cold, best of the
other two is "hot"), against:
  * parquet  the file directly, through ClickBench's own DuckDB view
  * native   the same data loaded into a DuckDB table (load time recorded)

The view and the queries are fetched at run time from a pinned ClickBench
commit and are not copied into this repo (ClickBench is CC BY-NC-SA 4.0).
https://github.com/ClickHouse/ClickBench

Usage:
  python clickbench.py                     # full 100M-row file
  python clickbench.py --sample 1000000    # first N rows only (quick check)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.request

import duckdb

import bench

CLICKBENCH_SHA = "3d75dd960d5030bfbcfedf29115430be1ef5056b"
RAW = f"https://raw.githubusercontent.com/ClickHouse/ClickBench/{CLICKBENCH_SHA}/duckdb-parquet"
HITS_URL = "https://datasets.clickhouse.com/hits_compatible/hits.parquet"


# Some hosts refuse urllib's default User-Agent with 403.
UA = {"User-Agent": "duckdb-scenarios-explorer/13 (+https://github.com/liangruibupt/duckdb-scenarios-explorer)"}


def _open(url: str, timeout: int):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def fetch_text(url: str) -> str:
    with _open(url, 60) as r:
        return r.read().decode()


def download(url: str, dest: pathlib.Path) -> float:
    if dest.exists():
        return 0.0
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    t0 = time.perf_counter()
    with _open(url, 120) as r, open(tmp, "wb") as f:
        while chunk := r.read(16 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return time.perf_counter() - t0


def split_sql(text: str) -> list[str]:
    return [s.strip() for s in text.split(";") if s.strip()]


def view_sql(create_sql: str, parquet: pathlib.Path) -> list[str]:
    """ClickBench's create.sql with the file path pointed at our copy."""
    return split_sql(create_sql.replace("'hits.parquet'", f"'{parquet.as_posix()}'"))


def run(con: duckdb.DuckDBPyConnection, queries: list[str], temp_dir: pathlib.Path,
        repeats: int) -> list[dict]:
    out = []
    for i, sql in enumerate(queries):
        times, err, rows = [], None, 0
        with bench.Sampler(con, temp_dir) as s:
            for _ in range(repeats):
                t0 = time.perf_counter()
                try:
                    rows = len(con.execute(sql).fetchall())
                except duckdb.Error as e:
                    err = f"{type(e).__name__}: {e}".splitlines()[0][:300]
                    break
                times.append(round(time.perf_counter() - t0, 3))
        rec = {
            "query": i, "times": times,
            "cold_seconds": times[0] if times else None,
            "hot_seconds": min(times[1:]) if len(times) > 1 else None,
            "rows": rows,
            "peak_rss_gb": round(s.peak_rss / 2**30, 2),
            "peak_spill_gb": round(max(s.peak_spill, s.peak_tmpdir) / 2**30, 2),
            "ok": err is None, "error": err,
        }
        out.append(rec)
        print(f"  Q{i:02d} cold {rec['cold_seconds']}s hot {rec['hot_seconds']}s "
              f"{'ok' if err is None else 'FAILED ' + err}", flush=True)
    return out


def summarize(recs: list[dict]) -> dict:
    hot = [r["hot_seconds"] for r in recs if r["hot_seconds"] is not None]
    cold = [r["cold_seconds"] for r in recs if r["cold_seconds"] is not None]
    return {
        "queries_ok": sum(r["ok"] for r in recs),
        "sum_cold_seconds": round(sum(cold), 2),
        "sum_hot_seconds": round(sum(hot), 2),
        "max_peak_rss_gb": max((r["peak_rss_gb"] for r in recs), default=0),
    }


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=0, help="use only the first N rows")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--memory-limit", default=None)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--sources", default="parquet,native")
    ap.add_argument("--hits-url", default=HITS_URL)
    ap.add_argument("--data-dir", default=str(bench.DATA))
    ap.add_argument("--results-dir", default=str(bench.RESULTS))
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)

    data = pathlib.Path(a.data_dir)
    hits = data / "hits.parquet"
    temp_dir = data / "tmp_clickbench"
    cfg = dict(memory_limit=a.memory_limit, threads=a.threads, temp_dir=temp_dir, max_temp=None)

    print(f"ClickBench: downloading {a.hits_url}", flush=True)
    dl_s = download(a.hits_url, hits)
    create_sql = fetch_text(f"{RAW}/create.sql")
    queries = split_sql(fetch_text(f"{RAW}/queries.sql"))
    assert len(queries) == 43, f"expected 43 ClickBench queries, got {len(queries)}"

    if a.sample:
        # Optional quick mode: a smaller Parquet with the first N rows.
        small = data / f"hits_{a.sample}.parquet"
        if not small.exists():
            c = duckdb.connect()
            c.execute(f"COPY (SELECT * FROM read_parquet('{hits.as_posix()}') LIMIT {a.sample}) "
                      f"TO '{small.as_posix()}' (FORMAT parquet)")
            c.close()
        hits = small

    result = {
        "benchmark": "clickbench", "clickbench_commit": CLICKBENCH_SHA,
        "tag": a.tag, "machine": bench.machine_info(),
        "config": {"memory_limit": a.memory_limit, "threads": a.threads,
                   "repeats": a.repeats, "sample_rows": a.sample},
        "download_seconds": round(dl_s, 1),
        "parquet_gb": round(hits.stat().st_size / 2**30, 2),
        "runs": {},
    }

    for source in [s for s in a.sources.split(",") if s]:
        con = duckdb.connect()
        bench.configure(con, **cfg)
        for stmt in view_sql(create_sql, hits):
            con.execute(stmt)
        load_s = None
        if source == "native":
            # Materialize the view into a real DuckDB table, then query that.
            t0 = time.perf_counter()
            db_file = data / "clickbench.duckdb"
            if db_file.exists():
                db_file.unlink()
            con.execute(f"ATTACH '{db_file.as_posix()}' AS cb")
            con.execute("CREATE TABLE cb.hits AS SELECT * FROM hits")
            con.execute("CHECKPOINT cb")
            load_s = round(time.perf_counter() - t0, 1)
            con.execute("DROP VIEW hits")
            con.execute("USE cb")
            # Re-create ClickBench's helper macros (e.g. toDateTime) in the
            # attached database so the queries resolve them after USE cb.
            for stmt in view_sql(create_sql, hits):
                if stmt.upper().startswith("CREATE MACRO"):
                    con.execute(stmt)
        print(f"Running 43 queries x{a.repeats} (source={source})", flush=True)
        recs = run(con, queries, temp_dir, a.repeats)
        con.close()
        result["runs"][source] = {"load_seconds": load_s, **summarize(recs), "queries": recs}

    out_dir = pathlib.Path(a.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"clickbench{'_' + a.tag if a.tag else ''}"
    pathlib.Path(f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {stem}.json", flush=True)
    return result


if __name__ == "__main__":
    main()
