#!/usr/bin/env python3
"""
Scenario 10 (cloud) -- run the REAL Aurora PostgreSQL + embedded-DuckDB flow.

Connects to an Aurora PostgreSQL 17.11+/18.6+ cluster, enables the
`aurora_analytics` extension (DuckDB embedded in Aurora), creates a FOREIGN TABLE
over Parquet/Iceberg in your data lake, and runs the unified query. This is the
cloud analogue of datalake_query.py's local DuckDB demo.

Prerequisites (you do these once, outside this script):
  - Aurora PostgreSQL cluster on 17 (>=17.11) or 18 (>=18.6).
  - An IAM role with the `AuroraAnalytics` feature attached to the cluster,
    granting read access to your S3 location (and Glue Data Catalog if used).
  - A reachable endpoint + credentials (this script reads them from env).

  export PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...
  export LAKE_LOCATION='s3://my-bucket/finance/transaction_history.parquet'
  export LAKE_FORMAT=parquet            # or: iceberg
  python cloud_aurora.py

Needs `psycopg` (psycopg3) or `psycopg2`. Install: pip install "psycopg[binary]".
Docs: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/
"""
from __future__ import annotations
import os
import sys

LAKE_LOCATION = os.environ.get("LAKE_LOCATION", "")
LAKE_FORMAT = os.environ.get("LAKE_FORMAT", "parquet")
CUSTOMER = os.environ.get("CUSTOMER_ID", "C-1001")


def _connect():
    try:
        import psycopg                      # psycopg3
        return psycopg.connect(autocommit=True)   # reads PG* env vars
    except ModuleNotFoundError:
        pass
    try:
        import psycopg2                     # fallback
        dsn = (f"host={os.environ['PGHOST']} port={os.environ.get('PGPORT','5432')} "
               f"dbname={os.environ['PGDATABASE']} user={os.environ['PGUSER']} "
               f"password={os.environ.get('PGPASSWORD','')}")
        c = psycopg2.connect(dsn)
        c.autocommit = True
        return c
    except ModuleNotFoundError:
        print("Need psycopg (psycopg3) or psycopg2: pip install 'psycopg[binary]'")
        sys.exit(2)


def main() -> None:
    if not LAKE_LOCATION:
        print("Set LAKE_LOCATION=s3://bucket/history.parquet [LAKE_FORMAT=parquet|iceberg] "
              "and PG* connection env vars first.")
        sys.exit(2)

    con = _connect()
    cur = con.cursor()

    # 1) Embed DuckDB in Aurora.
    cur.execute("CREATE EXTENSION IF NOT EXISTS aurora_analytics;")

    # 2) FOREIGN TABLE over the lake. Empty column list () => Aurora auto-reads
    #    the schema from Parquet/Iceberg metadata, no manual column DDL.
    cur.execute("DROP FOREIGN TABLE IF EXISTS transaction_history;")
    cur.execute(f"""
        CREATE FOREIGN TABLE transaction_history ()
        SERVER aurora_analytics_server
        OPTIONS (location '{LAKE_LOCATION}', format '{LAKE_FORMAT}');
    """)

    # 3) The unified query -- live operational rows UNION the lake, one statement.
    cur.execute(f"""
        SELECT merchant, category, amount, transaction_date, 'recent' AS source
          FROM recent_transactions
         WHERE customer_id = %(cid)s
        UNION ALL
        SELECT merchant, category, amount, transaction_date, 'historical' AS source
          FROM transaction_history
         WHERE customer_id = %(cid)s
           AND transaction_date >= CURRENT_DATE - INTERVAL '5 years'
         ORDER BY transaction_date DESC
         LIMIT 15;
    """, {"cid": CUSTOMER})
    print(f"# Unified timeline for {CUSTOMER} (Aurora rows + lake via DuckDB):")
    for row in cur.fetchall():
        print("  ", row)

    # 4) Per-query engine stats: rows scanned, S3 bytes read, cache hits.
    try:
        cur.execute("SELECT * FROM aurora_analytics_stat_statements();")
        print("\n# aurora_analytics_stat_statements():")
        for row in cur.fetchall():
            print("  ", row)
    except Exception as e:                   # view shape varies by version
        print(f"\n(stat view unavailable: {e})")

    print("\nDuckDB ran the lake scan inside Aurora; no data left S3 except the "
          "bytes the query needed, and no reverse-ETL pipeline was involved.")


if __name__ == "__main__":
    main()
