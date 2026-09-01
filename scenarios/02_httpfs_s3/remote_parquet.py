#!/usr/bin/env python3
"""
Scenario 02 -- Query Parquet on S3 in place with DuckDB's httpfs extension.

The "query the data lake without downloading it" pattern:
  - read_parquet('s3://...') straight off S3, no download, no cluster
  - projection + predicate push-down over S3 range requests (only the touched
    columns / row groups are fetched)
  - multi-file globs and hive-partition pruning (year=/month=)

Target bucket/prefix (real, account 747411437379, us-east-1):
    s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/

If the data isn't there yet, run ./seed_s3.sh once (it uploads the local taxi
Parquet in a hive-partitioned layout). Credentials come from the default AWS
chain (env vars or the EC2 instance role) via DuckDB's credential_chain secret.
"""
from __future__ import annotations
import subprocess
import sys
import time
import duckdb

BUCKET = "cdh-ingest-demo"
PREFIX = "duckdb-demo/nyc_taxi"
REGION = "us-east-1"
GLOB = f"s3://{BUCKET}/{PREFIX}/**/*.parquet"        # year=YYYY/month=MM/*.parquet


def s3_has_data() -> bool:
    out = subprocess.run(
        ["aws", "s3", "ls", f"s3://{BUCKET}/{PREFIX}/", "--recursive"],
        capture_output=True, text=True)
    return ".parquet" in out.stdout


def timed(con, label, sql):
    t0 = time.perf_counter()
    df = con.execute(sql).fetchdf()
    print(f"\n# {label}  [{(time.perf_counter()-t0)*1000:,.0f} ms]")
    print(df.to_string(index=False))
    return df


def main() -> None:
    if not s3_has_data():
        print(f"No Parquet under s3://{BUCKET}/{PREFIX}/ yet.\n"
              f"Seed it once with:  ./seed_s3.sh\n"
              f"(uploads the local taxi Parquet as year=2024/month=01/part.parquet)")
        sys.exit(2)

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    # Use the ambient AWS credential chain (instance role / env vars).
    con.execute(f"CREATE OR REPLACE SECRET s3 "
                f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")

    timed(con, "Row count read straight off S3 (no download)",
          f"SELECT count(*) AS rows FROM read_parquet('{GLOB}')")

    # Only 3 columns are decoded; DuckDB fetches just the needed row groups.
    timed(con, "Aggregate touching 3 columns (pushed down over S3)",
          f"""SELECT payment_type, count(*) trips, round(avg(total_amount),2) avg_total
              FROM read_parquet('{GLOB}')
              WHERE fare_amount > 0
              GROUP BY payment_type ORDER BY trips DESC""")

    # Hive-partition pruning: the year=/month= path components become columns,
    # and a WHERE on them skips non-matching files entirely.
    timed(con, "Hive-partition columns exposed + pruned",
          f"""SELECT year, month, count(*) trips
              FROM read_parquet('{GLOB}', hive_partitioning=true)
              WHERE year = 2024
              GROUP BY year, month ORDER BY month""")

    print("\nDone -- queried S3 Parquet in place, no data left the bucket except "
          "the bytes the queries needed.")


if __name__ == "__main__":
    main()
