#!/usr/bin/env python3
"""
Scenario 03 -- DuckDB as a lightweight CSV -> Parquet ETL engine.

Raw data usually lands as untyped, row-oriented CSV. Converting it once to
typed, compressed, partitioned Parquet makes every later query far cheaper.
DuckDB does the whole clean -> cast -> partitioned-write in a single binary --
no Spark, no cluster. This is exactly what you'd run inside a Lambda (small /
streaming) or a Fargate task (big batch).

Fully self-contained: it synthesizes a deliberately messy CSV first, so you can
run it with no external data.

  python etl.py     # -> out/events/dt=YYYY-MM-DD/*.parquet  + a verification query
"""
from __future__ import annotations
import os
import random
import datetime as dt
import duckdb

RAW = "raw_events.csv"
OUT = "out/events"


def make_messy_csv(path: str, n: int = 50_000) -> None:
    """A CSV with the usual real-world mess: mixed case, blank fields,
    thousands separators, stray whitespace, a couple of bad rows."""
    random.seed(7)
    cats = ["Electronics", "electronics ", "BOOKS", "books", " Toys", "Home"]
    regions = ["us-east", "US-EAST", "eu-west", "ap-south", ""]
    start = dt.date(2024, 1, 1)
    with open(path, "w") as f:
        f.write("event_id,ts,category,region,amount,qty\n")
        for i in range(n):
            d = start + dt.timedelta(days=random.randint(0, 6))
            t = f"{d}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"
            cat = random.choice(cats)
            region = random.choice(regions)
            amount = f"{random.randint(1,9)},{random.randint(0,999):03d}.{random.randint(0,99):02d}"
            qty = random.choice([1, 2, 3, 5, 10, -1])          # -1 = bad
            # amount has a thousands-comma, so it MUST be quoted or the comma
            # would be read as a field delimiter.
            f.write(f'{i},{t},{cat},{region},"{amount}",{qty}\n')
        f.write("999999,not-a-date,,,,\n")                     # 1 junk row


def main() -> None:
    make_messy_csv(RAW)
    os.makedirs("out", exist_ok=True)
    con = duckdb.connect()

    # 1) INGEST: read_csv auto-detects types; keep amount as VARCHAR so we can
    #    strip the thousands separator ourselves.
    con.execute(f"""
        CREATE OR REPLACE VIEW raw AS
        SELECT * FROM read_csv('{RAW}',
            header=true,
            columns={{'event_id':'BIGINT','ts':'VARCHAR','category':'VARCHAR',
                      'region':'VARCHAR','amount':'VARCHAR','qty':'INTEGER'}},
            ignore_errors=true)          -- drop the structurally-bad junk row
    """)

    # 2) CLEAN + CAST: normalize text, parse timestamp, strip ',' from amount,
    #    drop invalid rows.
    con.execute("""
        CREATE OR REPLACE VIEW clean AS
        SELECT
            event_id,
            try_cast(ts AS TIMESTAMP)                          AS ts,
            lower(trim(category))                              AS category,
            nullif(lower(trim(region)), '')                    AS region,
            try_cast(replace(amount, ',', '') AS DECIMAL(10,2)) AS amount,
            qty
        FROM raw
        WHERE try_cast(ts AS TIMESTAMP) IS NOT NULL
          AND qty > 0
          AND try_cast(replace(amount, ',', '') AS DECIMAL(10,2)) IS NOT NULL
    """)

    raw_n = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    clean_n = con.execute("SELECT count(*) FROM clean").fetchone()[0]

    # 3) WRITE partitioned Parquet (one directory per day), zstd-compressed.
    con.execute(f"""
        COPY (SELECT *, ts::DATE AS dt FROM clean)
        TO '{OUT}' (FORMAT parquet, PARTITION_BY (dt),
                    COMPRESSION zstd, OVERWRITE_OR_IGNORE true)
    """)

    # 4) VERIFY: query the freshly-written Parquet back.
    parts = con.execute(
        f"SELECT count(*) FROM glob('{OUT}/**/*.parquet')").fetchone()[0]
    print(f"Ingested {raw_n:,} raw rows -> {clean_n:,} clean rows "
          f"(dropped {raw_n-clean_n:,}); wrote {parts} Parquet part-files.\n")

    df = con.execute(f"""
        SELECT dt, category,
               count(*) events, round(sum(amount),2) revenue
        FROM read_parquet('{OUT}/**/*.parquet', hive_partitioning=true)
        GROUP BY dt, category
        ORDER BY dt, revenue DESC
        LIMIT 12
    """).fetchdf()
    print("# Query over the partitioned Parquet output:")
    print(df.to_string(index=False))

    # Show the file-size win vs the source CSV.
    csv_sz = os.path.getsize(RAW)
    pq_sz = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(OUT) for f in fs if f.endswith(".parquet"))
    print(f"\nCSV {csv_sz/1e6:.2f} MB  ->  Parquet {pq_sz/1e6:.2f} MB "
          f"({csv_sz/pq_sz:.1f}x smaller, and columnar for fast scans).")


if __name__ == "__main__":
    main()
