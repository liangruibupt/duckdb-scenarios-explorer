#!/usr/bin/env python3
"""
Scenario 09 (cloud) -- read a REAL Amazon S3 Tables Iceberg table with DuckDB.

DuckDB attaches the S3 Tables Iceberg REST catalog and queries the managed table
in place (no Spark, no download). This is the cloud analogue of tables.py's local
DuckLake demo.

  export S3_TABLES_ARN=arn:aws:s3tables:us-east-1:<acct>:bucket/<name>
  export ICEBERG_TABLE=nyc.trips
  python cloud_s3tables.py
"""
from __future__ import annotations
import os
import sys
import duckdb

ARN = os.environ.get("S3_TABLES_ARN", "")
TABLE = os.environ.get("ICEBERG_TABLE", "nyc.trips")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def main() -> None:
    if not ARN:
        print("Set S3_TABLES_ARN=<bucket arn> [ICEBERG_TABLE=nyc.trips] first.")
        sys.exit(2)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws; "
                "INSTALL iceberg; LOAD iceberg;")
    con.execute(f"CREATE OR REPLACE SECRET s3 "
                f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
    con.execute(f"ATTACH '{ARN}' AS s3tbl (TYPE iceberg, ENDPOINT_TYPE s3_tables)")

    n = con.execute(f"SELECT count(*) FROM s3tbl.{TABLE}").fetchone()[0]
    print(f"# Live S3 Tables Iceberg table s3tbl.{TABLE}: {n:,} rows")
    df = con.execute(
        f"SELECT payment_type, count(*) trips, round(avg(total_amount),2) avg_total "
        f"FROM s3tbl.{TABLE} WHERE fare_amount > 0 "
        f"GROUP BY payment_type ORDER BY trips DESC").fetchdf()
    print(df.to_string(index=False))
    print("\nRead in place from a managed Iceberg table on S3 -- no download, no "
          "Spark; the catalog resolves the current snapshot's files.")


if __name__ == "__main__":
    main()
