#!/usr/bin/env python3
"""
Scenario 12 -- Run DuckDB analytics on Amazon DynamoDB data via a zero-ETL
integration to Apache Iceberg on Amazon S3 Tables.

AWS pattern (Sep-2026): keep operational traffic on DynamoDB; a zero-ETL
integration replicates the table (from PITR backups, so the table is unaffected)
into an Iceberg table on S3 Tables on a refresh interval (15 min default). A
DuckDB-in-Lambda function then serves ad-hoc SQL over that Iceberg data through
an IAM-authorized HTTPS endpoint -- or you attach the same catalog from anywhere
DuckDB runs.
    https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/

A key detail the integration handles: each item's TOP-LEVEL attributes are
flattened into typed Iceberg columns, attribute names arrive LOWERCASED (so a
DynamoDB `PK` becomes column `pk`), and DynamoDB type descriptors ({"N":"187.20"}
-> a numeric column) are unwrapped. You query plain typed rows -- no attribute
unwrapping in SQL.

This offline demo reproduces that end to end with no AWS: synthesize DynamoDB
items (with {"S":..}/{"N":..} descriptors), apply the zero-ETL FLATTENING
transform, land them in a local DuckLake managed Iceberg-style table, then run the
blog's headline query (revenue by category) plus a couple more. CI-friendly.

  python ddb_analytics.py
"""
from __future__ import annotations
import os
import random
import tempfile
import datetime as dt
import duckdb

CATEGORIES = ["toys", "sports", "books", "electronics", "home"]
STATUSES = ["placed", "shipped", "delivered", "returned"]


def synth_dynamodb_items(n: int = 5_000) -> list[dict]:
    """DynamoDB items as the SDK returns them: every attribute wrapped in a
    single-key type descriptor ({"S": str} / {"N": numeric-as-string})."""
    random.seed(12)
    items = []
    base = dt.datetime(2026, 8, 15, 9, 0, 0)
    for i in range(n):
        cust = f"CUST#{random.randint(1, 400):04d}"
        ts = base + dt.timedelta(minutes=random.randint(0, 60 * 24 * 60))
        items.append({
            "PK":       {"S": cust},
            "SK":       {"S": f"ORDER#{ts.isoformat()}#{i:06d}"},
            "order_id": {"S": f"{i:06d}"},
            "category": {"S": random.choice(CATEGORIES)},
            "status":   {"S": random.choice(STATUSES)},
            "amount":   {"N": f"{random.uniform(5, 500):.2f}"},
            "items":    {"N": str(random.randint(1, 6))},
        })
    return items


def zero_etl_flatten(items: list[dict]) -> list[dict]:
    """Model the zero-ETL integration's flattening: unwrap each top-level
    attribute's type descriptor to a native value, and lowercase the attribute
    name (PK -> pk). {"N": "187.20"} becomes a float; {"S": "toys"} a string.
    This is what lands as typed Iceberg columns -- not the wrapped form."""
    out = []
    for it in items:
        row = {}
        for name, desc in it.items():
            (typ, val), = desc.items()          # exactly one descriptor key
            if typ == "N":
                num = float(val)
                row[name.lower()] = int(num) if num.is_integer() else num
            else:                               # "S" (and other scalar types)
                row[name.lower()] = val
        out.append(row)
    return out


def connect_ducklake(tmp: str) -> duckdb.DuckDBPyConnection:
    """Offline stand-in for the S3 Tables Iceberg catalog: a local DuckLake
    managed table. In the cloud this is the zero-ETL-populated Iceberg table that
    DuckDB ATTACHes read-only (see cloud_ddb_lambda.py)."""
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    cat = os.path.join(tmp, "analytics.ducklake")
    data = os.path.join(tmp, "data")
    con.execute(f"ATTACH 'ducklake:{cat}' AS analytics (DATA_PATH '{data}')")
    con.execute("USE analytics")
    return con


def land_orders(con, rows: list[dict]) -> None:
    """Land the flattened rows as the integration's Iceberg table would appear:
    typed columns, lowercased names."""
    con.execute("""CREATE TABLE orders (
        pk VARCHAR, sk VARCHAR, order_id VARCHAR, category VARCHAR,
        status VARCHAR, amount DOUBLE, items INTEGER)""")
    con.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
        [(r["pk"], r["sk"], r["order_id"], r["category"],
          r["status"], r["amount"], r["items"]) for r in rows])


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        items = synth_dynamodb_items()
        rows = zero_etl_flatten(items)
        con = connect_ducklake(tmp)
        land_orders(con, rows)

        n = con.execute("SELECT count(*) FROM orders").fetchone()[0]
        print(f"# {n:,} DynamoDB items flattened by zero-ETL into typed Iceberg rows")
        print("#   DynamoDB 'PK' -> column 'pk'; {\"N\":\"187.20\"} -> numeric 'amount'\n")

        # The blog's headline query, verbatim shape: revenue by category.
        print("# Revenue by category (the blog's example query):")
        df = con.execute("""
            SELECT category, round(sum(amount), 2) AS revenue
              FROM orders
             GROUP BY category
             ORDER BY revenue DESC""").fetchdf()
        print(df.to_string(index=False))

        # A second analytical question the OLTP table should not serve directly.
        print("\n# Order volume by hour of day (analytical scan, not an OLTP read):")
        df2 = con.execute("""
            SELECT extract('hour' FROM strptime(
                       split_part(sk, '#', 2), '%Y-%m-%dT%H:%M:%S')) AS hour,
                   count(*) AS orders
              FROM orders
             GROUP BY hour ORDER BY hour LIMIT 8""").fetchdf()
        print(df2.to_string(index=False))

        # Status mix -- the kind of aggregate you run against the replica, never
        # against the live table.
        print("\n# Status mix:")
        df3 = con.execute("""
            SELECT status, count(*) AS n,
                   round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
              FROM orders GROUP BY status ORDER BY n DESC""").fetchdf()
        print(df3.to_string(index=False))

        print("\nDuckDB served analytical SQL over the zero-ETL Iceberg copy -- the")
        print("DynamoDB table kept serving operational traffic untouched (the")
        print("integration reads PITR backups). In the cloud this runs inside a")
        print("DuckDB Lambda behind an IAM function URL; see cloud_ddb_lambda.py.")


if __name__ == "__main__":
    main()
