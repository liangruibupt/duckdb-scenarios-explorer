#!/usr/bin/env python3
"""
Scenario 11 (cloud) -- the DuckDB-on-Glue ETL against a REAL Amazon S3 Tables
Iceberg table. This is the body you drop into a Glue 6.0 Python-shell job (or run
on ECS/EC2); it reads a raw CSV/Parquet drop from S3, transforms it with the SAME
`transform_sql` as the offline demo, and appends to an Iceberg table through the
S3 Tables REST catalog -- no Spark.

  export S3_TABLES_ARN=arn:aws:s3tables:us-east-1:<acct>:bucket/<name>
  export ICEBERG_TABLE=sales.daily          # <namespace>.<table>
  export RAW_SOURCE='s3://my-bucket/raw/sales_2026-10-20.csv'   # or a local file
  export AWS_REGION=us-east-1
  python cloud_glue_s3tables.py

In a Glue job the body after connect() is what matters; connection + extensions
are set up once at module load (outside the handler) so warm runs skip setup,
exactly as AWS recommends for the Lambda/Glue DuckDB pattern.
"""
from __future__ import annotations
import os
import sys
import duckdb

# Import the shared transform so the cloud job and the offline demo are provably
# the same SQL.
sys.path.insert(0, os.path.dirname(__file__))
from glue_etl import transform_sql          # noqa: E402

ARN = os.environ.get("S3_TABLES_ARN", "")
TABLE = os.environ.get("ICEBERG_TABLE", "sales.daily")
RAW_SOURCE = os.environ.get("RAW_SOURCE", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws; "
                "INSTALL iceberg; LOAD iceberg;")
    con.execute(f"CREATE OR REPLACE SECRET s3 "
                f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
    # S3 Tables Iceberg REST catalog -- writable from DuckDB (CREATE/INSERT).
    con.execute(f"ATTACH '{ARN}' AS s3tbl (TYPE iceberg, ENDPOINT_TYPE s3_tables)")
    return con


def main() -> None:
    if not ARN or not RAW_SOURCE:
        print("Set S3_TABLES_ARN=<bucket arn>, ICEBERG_TABLE=<ns.table> and "
              "RAW_SOURCE=<s3://.../raw.csv> first.")
        sys.exit(2)

    con = connect()
    # First run creates the table from the transform; later runs append. We probe
    # existence by trying a count and falling back to CREATE TABLE AS.
    exists = True
    try:
        con.execute(f"SELECT 1 FROM s3tbl.{TABLE} LIMIT 1")
    except Exception:
        exists = False

    if exists:
        con.execute(f"INSERT INTO s3tbl.{TABLE} {transform_sql(RAW_SOURCE)}")
        print(f"# Appended transformed rows to existing Iceberg table s3tbl.{TABLE}")
    else:
        con.execute(f"CREATE TABLE s3tbl.{TABLE} AS {transform_sql(RAW_SOURCE)}")
        print(f"# Created Iceberg table s3tbl.{TABLE} from the transform")

    n = con.execute(f"SELECT count(*) FROM s3tbl.{TABLE}").fetchone()[0]
    print(f"# s3tbl.{TABLE} now holds {n:,} rows")
    df = con.execute(
        f"SELECT category, count(*) orders, round(sum(revenue),2) revenue "
        f"FROM s3tbl.{TABLE} GROUP BY category ORDER BY revenue DESC").fetchdf()
    print(df.to_string(index=False))
    print("\nDuckDB transformed the raw drop and wrote a managed Iceberg table on "
          "S3 Tables -- a single Glue 6.0 worker, no Spark cluster, auto-compacted "
          "by S3 Tables and readable by Athena/Redshift/EMR too.")


if __name__ == "__main__":
    main()
