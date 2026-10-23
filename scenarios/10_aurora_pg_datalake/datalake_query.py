#!/usr/bin/env python3
"""
Scenario 10 -- Aurora PostgreSQL + embedded DuckDB: query operational data and
the data lake in ONE SQL statement (no reverse-ETL).

On 2026-09-30 AWS made DuckDB embedded *inside Aurora PostgreSQL* GA: you query
live operational rows (including uncommitted writes) together with Apache Iceberg
and Parquet data in Amazon S3 / S3 Tables / Glue Data Catalog, through ordinary
PostgreSQL syntax -- no pipeline duplicating the lake into the OLTP database.
    https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/

The Aurora flow (cloud, see cloud_aurora.py):
    CREATE EXTENSION aurora_analytics;           -- DuckDB embedded in Aurora
    CREATE FOREIGN TABLE transaction_history ()  -- empty () => schema auto-read
      SERVER aurora_analytics_server
      OPTIONS (location 's3://bucket/finance/history.parquet', format 'parquet');
    -- then a single query UNIONs Aurora's recent_transactions with the lake.

This script is the OFFLINE stand-in: the SAME shape -- a small, "hot" operational
table JOINed/UNIONed with a large historical Parquet "lake" -- proven locally with
one embedded DuckDB, which is exactly the engine Aurora now runs under the hood.
Fully self-contained (synthesizes both sides), so it runs with no AWS and in CI.

  python datalake_query.py
"""
from __future__ import annotations
import os
import random
import tempfile
import datetime as dt
import duckdb

CUSTOMER = "C-1001"


def seed(con: duckdb.DuckDBPyConnection, lake_dir: str,
         recent_n: int = 2_000, hist_n: int = 200_000) -> str:
    """Build the two sides of the demo:
      - recent_transactions: the last 7 days (the OLTP 'hot' table -- in Aurora
        this is a native PostgreSQL table on the writer/replica).
      - transaction_history: 5 years of history as Parquet on disk (the 'lake' --
        in Aurora a FOREIGN TABLE over Parquet/Iceberg in S3). Returns its path.
    Sizes are parameterized so tests can run a small version quickly.
    """
    random.seed(10)
    cats = ["grocery", "travel", "dining", "electronics", "fuel"]
    merchants = ["Acme", "Globex", "Initech", "Umbrella", "Soylent"]
    today = dt.date(2026, 10, 23)

    # OLTP side: a real table, last 7 days, several customers.
    con.execute("""CREATE TABLE recent_transactions (
        customer_id VARCHAR, merchant VARCHAR, category VARCHAR,
        amount DECIMAL(10,2), transaction_date DATE)""")
    rows = []
    for _ in range(recent_n):
        cid = random.choice([CUSTOMER, "C-1002", "C-1003", "C-1004"])
        d = today - dt.timedelta(days=random.randint(0, 6))
        rows.append((cid, random.choice(merchants), random.choice(cats),
                     round(random.uniform(4, 400), 2), d))
    con.executemany("INSERT INTO recent_transactions VALUES (?,?,?,?,?)", rows)

    # Lake side: 5 years of history, written once to partitioned Parquet.
    con.execute("""CREATE TABLE _hist (
        customer_id VARCHAR, merchant VARCHAR, category VARCHAR,
        amount DECIMAL(10,2), transaction_date DATE)""")
    hrows = []
    for _ in range(hist_n):
        cid = random.choice([CUSTOMER, "C-1002", "C-1003", "C-1004", "C-1005"])
        d = today - dt.timedelta(days=random.randint(8, 5 * 365))
        hrows.append((cid, random.choice(merchants), random.choice(cats),
                      round(random.uniform(4, 400), 2), d))
    con.executemany("INSERT INTO _hist VALUES (?,?,?,?,?)", hrows)
    path = os.path.join(lake_dir, "transaction_history.parquet")
    con.execute(f"COPY _hist TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
    con.execute("DROP TABLE _hist")
    return path


def unified_timeline(con, lake_parquet: str, customer: str = CUSTOMER) -> list:
    """The headline Aurora query: one statement, both sources. In Aurora this is
    literally `FROM recent_transactions ... UNION ALL ... FROM transaction_history`
    where the second table is a FOREIGN TABLE on Parquet in S3. Here the foreign
    table is read_parquet(...) -- same embedded DuckDB does the lake scan."""
    return con.execute(f"""
        SELECT merchant, category, amount, transaction_date, 'recent' AS source
          FROM recent_transactions
         WHERE customer_id = ?
        UNION ALL
        SELECT merchant, category, amount, transaction_date, 'historical' AS source
          FROM read_parquet('{lake_parquet}')
         WHERE customer_id = ?
           AND transaction_date >= CURRENT_DATE - INTERVAL '5 years'
        ORDER BY transaction_date DESC
        LIMIT 15
    """, [customer, customer]).fetchall()


def enrich_join(con, lake_parquet: str, customer: str = CUSTOMER) -> list:
    """Enrich live transactions with a historical aggregate per category -- an
    operational row JOINed to a lake-derived feature, the 'transaction context'
    use case AWS calls out. One query, no pre-materialized feature table."""
    return con.execute(f"""
        WITH hist_avg AS (
            SELECT category, round(avg(amount), 2) AS hist_avg_amount, count(*) AS hist_n
              FROM read_parquet('{lake_parquet}')
             WHERE customer_id = ?
             GROUP BY category)
        SELECT r.merchant, r.category, r.amount,
               h.hist_avg_amount,
               round(r.amount - h.hist_avg_amount, 2) AS delta_vs_hist
          FROM recent_transactions r
          JOIN hist_avg h USING (category)
         WHERE r.customer_id = ?
         ORDER BY abs(r.amount - h.hist_avg_amount) DESC
         LIMIT 10
    """, [customer, customer]).fetchall()


def main() -> None:
    con = duckdb.connect()
    with tempfile.TemporaryDirectory() as tmp:
        lake = seed(con, tmp)
        recent_n = con.execute("SELECT count(*) FROM recent_transactions").fetchone()[0]
        hist_n = con.execute(f"SELECT count(*) FROM read_parquet('{lake}')").fetchone()[0]
        print(f"# Operational table: {recent_n:,} recent rows (last 7 days)")
        print(f"# Data lake Parquet: {hist_n:,} historical rows (5 years)\n")

        print(f"# 1) Unified timeline for {CUSTOMER} -- ONE query, both sources")
        print("#    (in Aurora: recent_transactions UNION ALL a FOREIGN TABLE on S3)")
        for merchant, cat, amt, d, src in unified_timeline(con, lake):
            print(f"  {d}  {src:<10} {cat:<12} {merchant:<10} ${amt}")

        print(f"\n# 2) Live rows enriched with a 5-year historical average per category")
        print("#    (operational row JOIN lake-derived feature, no feature pipeline)")
        print(f"  {'merchant':<10} {'category':<12} {'amount':>8} {'hist_avg':>9} {'delta':>8}")
        for merchant, cat, amt, havg, delta in enrich_join(con, lake):
            print(f"  {merchant:<10} {cat:<12} {amt:>8} {havg:>9} {delta:>+8}")

        print("\nOne embedded DuckDB scanned the Parquet lake and joined it to live")
        print("operational rows in a single SQL statement -- the reverse-ETL pipeline")
        print("that used to copy history into the OLTP database is gone. Aurora runs")
        print("exactly this engine under `aurora_analytics`; see cloud_aurora.py.")


if __name__ == "__main__":
    main()
