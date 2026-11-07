"""Scenario 13 -- Overture Maps: query a ~579 GiB public Parquet lake in place on S3.

Nothing is downloaded up front. Each query reads `s3://overturemaps-us-west-2`
directly with httpfs (anonymous access), and the harness records, per query:
  * cold and warm wall time (warm = same query again, with DuckDB's caches)
  * bytes received over the network during the cold run (psutil), to compare
    with the size of the data the query is "over"
  * peak RSS

Run it in us-west-2 so the data does not cross regions.
Overture data: https://docs.overturemaps.org/ (ODbL / CDLA licenses per theme).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import duckdb
import psutil

import bench

RELEASE = "2026-10-21.0"
BUCKET = "s3://overturemaps-us-west-2/release"

# (name, what it shows, SQL). {places}/{buildings}/{segments} are Parquet globs.
QUERIES = [
    ("places_count", "row count from Parquet footers only (11 GiB theme)",
     "SELECT count(*) FROM read_parquet('{places}')"),
    ("places_top_categories", "one-column scan + GROUP BY over all places",
     "SELECT basic_category, count(*) n FROM read_parquet('{places}') "
     "GROUP BY 1 ORDER BY n DESC LIMIT 20"),
    ("buildings_count", "row count over 512 files (258 GiB theme), footers only",
     "SELECT count(*) FROM read_parquet('{buildings}')"),
    ("buildings_seattle_bbox", "bbox filter: row-group statistics skip most of the 258 GiB",
     "SELECT count(*) FROM read_parquet('{buildings}') "
     "WHERE bbox.xmin BETWEEN -122.46 AND -122.22 AND bbox.ymin BETWEEN 47.48 AND 47.74"),
    ("buildings_height_by_subtype", "two-column full scan + aggregate over every building",
     "SELECT subtype, count(*) n, count(height) with_height, round(avg(height), 2) avg_height "
     "FROM read_parquet('{buildings}') GROUP BY 1 ORDER BY n DESC"),
    ("segments_by_class", "two-column full scan over transportation segments (68 GiB theme)",
     "SELECT subtype, class, count(*) n FROM read_parquet('{segments}') "
     "GROUP BY ALL ORDER BY n DESC LIMIT 20"),
    ("segments_tokyo_bbox", "bbox filter + GROUP BY on road class around Tokyo",
     "SELECT class, count(*) n FROM read_parquet('{segments}') "
     "WHERE bbox.xmin BETWEEN 139.55 AND 139.95 AND bbox.ymin BETWEEN 35.50 AND 35.82 "
     "GROUP BY 1 ORDER BY n DESC"),
    ("extract_seattle_buildings", "extract a city to local Parquet (COPY ... TO)",
     "COPY (SELECT id, subtype, class, height, num_floors, geometry FROM read_parquet('{buildings}') "
     "WHERE bbox.xmin BETWEEN -122.46 AND -122.22 AND bbox.ymin BETWEEN 47.48 AND 47.74) "
     "TO '{out}/seattle_buildings.parquet' (FORMAT parquet)"),
]


def globs(release: str) -> dict:
    base = f"{BUCKET}/{release}"
    return {
        "places": f"{base}/theme=places/type=place/*",
        "buildings": f"{base}/theme=buildings/type=building/*",
        "segments": f"{base}/theme=transportation/type=segment/*",
    }


def timed(con, sql: str):
    net0 = psutil.net_io_counters().bytes_recv
    t0 = time.perf_counter()
    rows = con.execute(sql).fetchall()
    return time.perf_counter() - t0, psutil.net_io_counters().bytes_recv - net0, rows


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", default=RELEASE)
    ap.add_argument("--queries", default="all", help="'all' or comma-separated names")
    ap.add_argument("--memory-limit", default=None)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--data-dir", default=str(bench.DATA))
    ap.add_argument("--results-dir", default=str(bench.RESULTS))
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)

    data = pathlib.Path(a.data_dir)
    out = data / "overture_out"
    out.mkdir(parents=True, exist_ok=True)
    temp_dir = data / "tmp_overture"
    con = duckdb.connect()
    bench.configure(con, memory_limit=a.memory_limit, threads=a.threads,
                    temp_dir=temp_dir, max_temp=None)
    con.execute("INSTALL httpfs; LOAD httpfs")
    # Anonymous (public bucket): a config secret with only a region and no keys.
    con.execute("CREATE SECRET overture (TYPE s3, PROVIDER config, REGION 'us-west-2')")
    # Remote reads are latency-bound; more threads keep more requests in flight.
    if a.threads is None:
        con.execute(f"SET threads = {max(16, 4 * (psutil.cpu_count() or 4))}")

    g = globs(a.release)
    wanted = None if a.queries == "all" else set(a.queries.split(","))
    recs = []
    for name, why, sql_t in QUERIES:
        if wanted and name not in wanted:
            continue
        sql = sql_t.format(out=out.as_posix(), **g)
        rec = {"name": name, "what": why, "ok": True, "error": None}
        with bench.Sampler(con, temp_dir) as s:
            try:
                cold, net, rows = timed(con, sql)
                warm, net_warm, _ = timed(con, sql)
                rec.update(cold_seconds=round(cold, 2), warm_seconds=round(warm, 2),
                           network_gb_cold=round(net / 2**30, 3),
                           network_gb_warm=round(net_warm / 2**30, 3),
                           result=[list(map(str, r)) for r in rows[:20]])
            except duckdb.Error as e:
                rec.update(ok=False, error=f"{type(e).__name__}: {e}".splitlines()[0][:300])
        rec["peak_rss_gb"] = round(s.peak_rss / 2**30, 2)
        recs.append(rec)
        print(f"  {name:28s} cold {rec.get('cold_seconds')}s warm {rec.get('warm_seconds')}s "
              f"net {rec.get('network_gb_cold')} GB {'ok' if rec['ok'] else 'FAILED ' + rec['error']}",
              flush=True)
    con.close()

    result = {
        "benchmark": "overture", "release": a.release, "tag": a.tag,
        "machine": bench.machine_info(),
        "config": {"memory_limit": a.memory_limit, "threads": a.threads},
        "queries": recs,
        "queries_ok": sum(r["ok"] for r in recs),
    }
    out_dir = pathlib.Path(a.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"overture{'_' + a.tag if a.tag else ''}"
    pathlib.Path(f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {stem}.json", flush=True)
    return result


if __name__ == "__main__":
    main()
