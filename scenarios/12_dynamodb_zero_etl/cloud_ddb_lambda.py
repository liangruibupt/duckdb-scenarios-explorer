#!/usr/bin/env python3
"""
Scenario 12 (cloud) -- query the REAL zero-ETL Iceberg table on S3 Tables that a
DynamoDB -> S3 Tables integration populates, with DuckDB.

Two ways to use this:
  1. As a local client: attach the S3 Tables catalog with your own credentials
     and query the table the integration created, from your laptop/ECS/EC2.
  2. As the body of the DuckDB-in-Lambda query function behind an IAM-authorized
     function URL -- the read-only lockdown below is exactly what AWS's sample
     handler applies so the SQL-accepting endpoint can only READ the catalog.

  export S3_TABLES_ARN=arn:aws:s3tables:us-east-1:<acct>:bucket/<name>
  export DDB_NAMESPACE=zetl_xxxxxxxx          # printed by the sample's status.py
  export DDB_TABLE=ddbduckdbanalytics_orders
  export AWS_REGION=us-east-1
  python cloud_ddb_lambda.py

Deploy the full integration + Lambda from:
  https://github.com/aws-samples/aws-dynamodb-examples/tree/master/infrastructure_as_code/cdk/ddb-duckdb-analytics
"""
from __future__ import annotations
import os
import sys
import duckdb

ARN = os.environ.get("S3_TABLES_ARN", "")
NAMESPACE = os.environ.get("DDB_NAMESPACE", "")
TABLE = os.environ.get("DDB_TABLE", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def connect_readonly() -> duckdb.DuckDBPyConnection:
    """The sample Lambda handler's setup: attach the catalog READ_ONLY, then lock
    the engine down so a SQL-accepting endpoint can do nothing but read it."""
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws; "
                "INSTALL avro; LOAD avro; INSTALL iceberg; LOAD iceberg;")
    con.execute(f"CREATE SECRET (TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
    con.execute(f"ATTACH '{ARN}' AS analytics "
                f"(TYPE iceberg, ENDPOINT_TYPE s3_tables, READ_ONLY)")
    # Lockdown (verbatim from the AWS sample) -- refuse local files, config
    # changes, writes, and community extensions.
    con.execute("SET disabled_filesystems = 'LocalFileSystem'")
    con.execute("SET autoinstall_known_extensions = false")
    con.execute("SET autoload_known_extensions = false")
    con.execute("SET allow_community_extensions = false")
    con.execute("SET lock_configuration = true")
    return con


def main() -> None:
    if not (ARN and NAMESPACE and TABLE):
        print("Set S3_TABLES_ARN, DDB_NAMESPACE and DDB_TABLE "
              "(the namespace/table the zero-ETL integration created).")
        sys.exit(2)

    con = connect_readonly()
    fq = f"analytics.{NAMESPACE}.{TABLE}"

    n = con.execute(f"SELECT count(*) FROM {fq}").fetchone()[0]
    print(f"# {fq}: {n:,} rows replicated from DynamoDB via zero-ETL\n")

    print("# Revenue by category:")
    df = con.execute(
        f"SELECT category, round(sum(amount),2) AS revenue "
        f"FROM {fq} GROUP BY category ORDER BY revenue DESC").fetchdf()
    print(df.to_string(index=False))

    print("\nRead straight off the Iceberg table on S3 Tables -- the DynamoDB "
          "table never saw these scans (the integration reads PITR backups). The "
          "same table is also queryable by Athena, Redshift, EMR and Spark.")


if __name__ == "__main__":
    main()
