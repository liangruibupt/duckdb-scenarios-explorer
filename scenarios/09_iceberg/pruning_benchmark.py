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


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect()
        # build a hive-partitioned Parquet dataset: one file per day
        con.execute(f"""COPY (
            SELECT (i % {PER_DAY}) id,
                   DATE '2024-01-01' + (i // {PER_DAY})::INT AS dt,
                   (i % 100) * 1.0 amt
            FROM range({DAYS * PER_DAY}) t(i)
        ) TO '{tmp}/pq' (FORMAT parquet, PARTITION_BY (dt), OVERWRITE_OR_IGNORE true)""")
        n_files = len(_glob.glob(f"{tmp}/pq/**/*.parquet", recursive=True))

        # A) raw Parquet glob: must enumerate all part-files then prune
        glob = f"{tmp}/pq/**/*.parquet"
        q_glob = (f"SELECT count(*) FROM read_parquet('{glob}', hive_partitioning=true) "
                  f"WHERE dt = DATE '2024-05-01'")
        con.execute(q_glob)   # warm
        t_glob = _best(lambda: con.execute(q_glob).fetchone())

        # B) DuckLake managed table: metadata pruning, no directory LIST
        con.execute("INSTALL ducklake; LOAD ducklake;")
        con.execute(f"ATTACH 'ducklake:{tmp}/c.ducklake' AS lake (DATA_PATH '{tmp}/ld')")
        con.execute("USE lake")
        con.execute(f"CREATE TABLE events AS SELECT * FROM read_parquet('{glob}', hive_partitioning=true)")
        q_lake = "SELECT count(*) FROM events WHERE dt = DATE '2024-05-01'"
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
    print("\n  Honest read: on LOCAL disk with {0} files the LIST is cheap, so the "
          "end-to-end times are close. The real win shows on S3, where LIST is a "
          "network round-trip per 1000 keys and file counts reach tens of "
          "thousands — there the glob's O(files) enumeration dominates and "
          "metadata pruning (a single manifest read) wins by a wide margin. "
          "The mechanism, not this local number, is the point."
          .format(n_files))


if __name__ == "__main__":
    main()
