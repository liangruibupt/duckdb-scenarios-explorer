#!/usr/bin/env python3
"""
Scenario 09 -- metadata pruning vs raw-Parquet LIST, a benchmark.

Builds a dataset split into MANY Parquet part-files (one per partition), then
runs the SAME selective query two ways:
  A) raw Parquet glob  -> the engine must LIST the prefix into a file list, then
     open footers; the cost scales with the number of files it has to enumerate.
  B) DuckLake table    -> the catalog + manifest already know which files (and
     their stats) match; it prunes from metadata without LISTing the directory.

Prints the file fan-out and best-of-N timings so the difference is concrete.

  python pruning_benchmark.py
"""
from __future__ import annotations
import glob as _glob
import os
import tempfile
import time
import duckdb

DAYS = 180          # 180 partition files
PER_DAY = 2000
REPEAT = 5


def _best(fn):
    best = float("inf")
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1000


def main(days: int = DAYS, per_day: int = PER_DAY) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect()
        # build a hive-partitioned Parquet dataset: one file per day
        con.execute(f"""COPY (
            SELECT (i % {per_day}) id,
                   DATE '2024-01-01' + (i // {per_day})::INT AS dt,
                   (i % 100) * 1.0 amt
            FROM range({days * per_day}) t(i)
        ) TO '{tmp}/pq' (FORMAT parquet, PARTITION_BY (dt), OVERWRITE_OR_IGNORE true)""")
        n_files = len(_glob.glob(f"{tmp}/pq/**/*.parquet", recursive=True))

        # a target day guaranteed to exist for any `days` (the midpoint)
        import datetime as _dt
        target = (_dt.date(2024, 1, 1) + _dt.timedelta(days=days // 2)).isoformat()

        # A) raw Parquet glob: must enumerate all part-files then prune
        glob = f"{tmp}/pq/**/*.parquet"
        q_glob = (f"SELECT count(*) FROM read_parquet('{glob}', hive_partitioning=true) "
                  f"WHERE dt = DATE '{target}'")
        con.execute(q_glob)   # warm
        t_glob = _best(lambda: con.execute(q_glob).fetchone())

        # B) DuckLake managed table: metadata pruning, no directory LIST
        con.execute("INSTALL ducklake; LOAD ducklake;")
        con.execute(f"ATTACH 'ducklake:{tmp}/c.ducklake' AS lake (DATA_PATH '{tmp}/ld')")
        con.execute("USE lake")
        con.execute(f"CREATE TABLE events AS SELECT * FROM read_parquet('{glob}', hive_partitioning=true)")
        q_lake = f"SELECT count(*) FROM events WHERE dt = DATE '{target}'"
        con.execute(q_lake)   # warm
        t_lake = _best(lambda: con.execute(q_lake).fetchone())

        fc = con.execute("SELECT file_count FROM ducklake_table_info('lake') "
                         "WHERE table_name='events'").fetchone()[0]

        # Isolate the signal that actually scales: enumerating the raw files.
        # glob() over the prefix is the LIST the Parquet path pays every query;
        # the DuckLake path pays it ONCE at ingest, never per query.
        def enumerate_parquet():
            return con.execute(f"SELECT count(*) FROM glob('{glob}')").fetchone()
        t_list = _best(enumerate_parquet)

    print(f"Dataset: {DAYS * PER_DAY:,} rows across {n_files} Parquet part-files "
          f"(one per day).\n")
    print(f"  A) raw Parquet glob query : {t_glob:6.1f} ms  "
          f"(LIST {n_files} files + open footers, EVERY query)")
    print(f"  B) DuckLake metadata query: {t_lake:6.1f} ms  "
          f"(catalog knows files+stats; {fc} logical file, no per-query LIST)")
    print(f"  raw-file enumeration cost : {t_list:6.1f} ms  "
          f"(the O(files) LIST the glob pays each time; DuckLake pays it once)")
    ratio = (t_glob / t_lake) if t_lake else float("inf")
    if ratio >= 3:
        print(f"\n  -> metadata pruning is {ratio:.0f}x faster at {n_files} files: "
              f"the glob's cost is almost entirely the O(files) LIST it pays every "
              f"query, while DuckLake paid it once at ingest and reads a manifest.")
    else:
        print(f"\n  Honest read: on LOCAL disk with {n_files} files the LIST is "
              f"cheap ({ratio:.1f}x), so the end-to-end times are close. Raise "
              f"--files (e.g. 10000) to expose the gap; on S3, where LIST is a "
              f"network round-trip per 1000 keys, it shows far sooner. The "
              f"mechanism (O(files) LIST every query vs a single manifest read) "
              f"is the point.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="metadata pruning vs raw-Parquet LIST")
    ap.add_argument("--files", type=int, default=DAYS,
                    help=f"number of Parquet part-files (one per day; default {DAYS})")
    ap.add_argument("--per-file", type=int, default=PER_DAY,
                    help=f"rows per part-file (default {PER_DAY})")
    a = ap.parse_args()
    main(days=a.files, per_day=a.per_file)
