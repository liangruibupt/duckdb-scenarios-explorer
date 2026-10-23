#!/usr/bin/env python3
"""
Scenario 11 -- DuckDB as the transform engine for a cost-effective AWS Glue 6.0
ETL job writing Apache Iceberg tables on Amazon S3 Tables.

AWS's Oct-2026 guidance: for scheduled SQL transformations, DuckDB on AWS Glue
6.0 is a lightweight, low-cost alternative to a Spark cluster -- faster iteration
and lower operational cost for the common "read raw -> clean/aggregate -> write
Iceberg" job. A single Glue Python-shell / 6.0 worker runs DuckDB in-process; no
cluster to spin up.
    https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue

The transform is PLAIN DuckDB SQL (`transform_sql` below), identical whether it
runs in a Glue job against S3 Tables (cloud_glue_s3tables.py) or here offline
against a local DuckLake managed table (the repo's offline Iceberg stand-in, same
convention as scenarios 03/09). That portability is the point: develop and test
the job's SQL locally in CI, deploy the exact same SQL to Glue.

Self-contained: synthesizes a raw daily sales drop, transforms it, writes a
managed (snapshotted, time-travellable) table, appends a second day, and proves
both the aggregate result and that each append is its own Iceberg-style snapshot.

  python glue_etl.py
"""
from __future__ import annotations
import os
import random
import tempfile
import datetime as dt
import duckdb

RAW_COLS = ("order_id BIGINT, ts VARCHAR, store VARCHAR, "
            "category VARCHAR, units VARCHAR, unit_price VARCHAR")


def make_raw_drop(path: str, day: dt.date, n: int = 40_000) -> None:
    """A raw daily CSV drop as it lands in S3: untyped, some mess (blank store,
    thousands-comma price, a bad units value)."""
    random.seed(hash(day) & 0xFFFF)
    stores = ["NYC-01", "nyc-01 ", "SEA-02", "", "AUS-03"]
    cats = ["beverages", "Beverages", "snacks", "HOME", "home "]
    with open(path, "w") as f:
        f.write("order_id,ts,store,category,units,unit_price\n")
        for i in range(n):
            t = f"{day}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"
            units = random.choice([1, 2, 3, 4, -1])          # -1 = bad
            price = f"{random.randint(1,3)},{random.randint(0,999):03d}.{random.randint(0,99):02d}"
            f.write(f'{i},{t},{random.choice(stores)},{random.choice(cats)},{units},"{price}"\n')


def transform_sql(raw_csv: str) -> str:
    """The job's transform, as a single DuckDB SELECT. This string is what you
    deploy to Glue unchanged -- clean/cast the raw drop into typed, normalized
    rows ready to append to the Iceberg table."""
    return f"""
        SELECT
            order_id,
            try_cast(ts AS TIMESTAMP)                                AS ts,
            ts::DATE                                                 AS dt,
            nullif(lower(trim(store)), '')                           AS store,
            lower(trim(category))                                    AS category,
            try_cast(units AS INTEGER)                               AS units,
            try_cast(replace(unit_price, ',', '') AS DECIMAL(10,2))  AS unit_price,
            round(try_cast(units AS INTEGER)
                  * try_cast(replace(unit_price, ',', '') AS DECIMAL(10,2)), 2) AS revenue
        FROM read_csv('{raw_csv}', header=true,
             columns={{'order_id':'BIGINT','ts':'VARCHAR','store':'VARCHAR',
                       'category':'VARCHAR','units':'VARCHAR','unit_price':'VARCHAR'}},
             ignore_errors=true)
        WHERE try_cast(units AS INTEGER) > 0
          AND try_cast(ts AS TIMESTAMP) IS NOT NULL
          AND nullif(lower(trim(store)), '') IS NOT NULL
    """


def connect_ducklake(tmp: str) -> duckdb.DuckDBPyConnection:
    """Offline Iceberg stand-in: a local DuckLake managed table (SQL catalog +
    Parquet). In Glue this is an ATTACH of the S3 Tables Iceberg REST catalog."""
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    cat = os.path.join(tmp, "sales.ducklake")
    data = os.path.join(tmp, "data")
    con.execute(f"ATTACH 'ducklake:{cat}' AS lake (DATA_PATH '{data}')")
    con.execute("USE lake")
    return con


def snapshots(con) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('lake') ORDER BY snapshot_id"
    ).fetchall()]


def run_job(con, raw_csv: str, first: bool) -> None:
    """One Glue job run: CREATE the managed table on the first run, then append
    the transformed rows (each append = a new Iceberg snapshot)."""
    if first:
        con.execute(f"CREATE TABLE sales AS {transform_sql(raw_csv)}")
    else:
        con.execute(f"INSERT INTO sales {transform_sql(raw_csv)}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        con = connect_ducklake(tmp)
        day1 = dt.date(2026, 10, 20)
        day2 = dt.date(2026, 10, 21)
        raw1 = os.path.join(tmp, "sales_2026-10-20.csv")
        raw2 = os.path.join(tmp, "sales_2026-10-21.csv")
        make_raw_drop(raw1, day1)
        make_raw_drop(raw2, day2)

        # Day 1 job run
        run_job(con, raw1, first=True)
        n1 = con.execute("SELECT count(*) FROM sales").fetchone()[0]
        snap1 = max(snapshots(con))
        print(f"# Glue run 1 ({day1}): appended {n1:,} clean rows  "
              f"-> Iceberg snapshot {snap1}")

        # Day 2 job run
        run_job(con, raw2, first=False)
        n2 = con.execute("SELECT count(*) FROM sales").fetchone()[0]
        snap2 = max(snapshots(con))
        print(f"# Glue run 2 ({day2}): table now {n2:,} rows             "
              f"-> Iceberg snapshot {snap2}")

        # Analytical result over the managed table
        print("\n# Revenue by category (over the managed Iceberg table):")
        df = con.execute("""
            SELECT category, count(*) AS orders, round(sum(revenue), 2) AS revenue
              FROM sales GROUP BY category ORDER BY revenue DESC""").fetchdf()
        print(df.to_string(index=False))

        # Time-travel: the table AS OF run 1 is day-1 only -- what Spark+raw
        # Parquet cannot give you without a table format.
        n_at_1 = con.execute(
            f"SELECT count(*) FROM sales AT (VERSION => {snap1})").fetchone()[0]
        print(f"\n# Time-travel to snapshot {snap1} (end of run 1): "
              f"{n_at_1:,} rows (day 1 only)")
        print("\nSame DuckDB SQL, no Spark cluster: a Glue 6.0 worker ran the "
              "transform in-process and wrote a snapshotted Iceberg table.")
        print("Deploy transform_sql() unchanged to Glue; see cloud_glue_s3tables.py.")


if __name__ == "__main__":
    main()
