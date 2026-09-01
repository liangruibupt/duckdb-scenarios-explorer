#!/usr/bin/env python3
"""
Scenario 05 -- Zero-copy SQL over in-memory Pandas DataFrames.

DuckDB can query a Pandas DataFrame directly, by variable name, with no copy and
no "load into a table" step -- the DataFrame's Arrow-backed buffers are scanned
in place. This is the data-science superpower: stay in Python, but reach for SQL
(joins, window functions, aggregates) exactly where Pandas gets awkward, and get
the result back as a DataFrame.

Shown here:
  1. SQL directly over a DataFrame (`FROM df`)
  2. DataFrame  JOIN  Parquet-on-disk in one query (mix in-memory + files)
  3. A window function that is verbose in Pandas, one line in SQL
  4. Result handed back to Pandas (.df()) and to Arrow (.arrow())

Self-contained: builds its own DataFrames; the optional Parquet join uses
scenario 01's taxi file if present, else falls back to an in-memory dim table.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import duckdb

TAXI = "../01_nyc_taxi/data/yellow_2024-01.parquet"


def main() -> None:
    rng = np.random.default_rng(42)
    n = 100_000
    # A synthetic "orders" DataFrame living purely in memory.
    orders = pd.DataFrame({
        "order_id": np.arange(n),
        "customer_id": rng.integers(1, 5_000, n),
        "region_id": rng.integers(1, 6, n),
        "amount": rng.gamma(2.0, 50.0, n).round(2),
        "ts": pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 30*24*3600, n), unit="s"),
    })
    # A tiny in-memory dimension DataFrame.
    regions = pd.DataFrame({
        "region_id": [1, 2, 3, 4, 5],
        "region": ["us-east", "us-west", "eu-west", "ap-south", "sa-east"],
    })

    con = duckdb.connect()

    # 1) SQL straight over the DataFrame -- referenced by its Python name.
    print("# 1. Aggregate directly over the in-memory DataFrame")
    print(con.execute("""
        SELECT region_id, count(*) orders, round(avg(amount),2) avg_amt,
               round(sum(amount),0) revenue
        FROM orders GROUP BY region_id ORDER BY revenue DESC
    """).df().to_string(index=False))

    # 2) Join the in-memory DataFrame to the in-memory dim -- no registration,
    #    both are just names in scope.
    print("\n# 2. DataFrame JOIN DataFrame (named in scope, zero copy)")
    print(con.execute("""
        SELECT r.region, count(*) orders, round(sum(o.amount),0) revenue
        FROM orders o JOIN regions r USING (region_id)
        GROUP BY r.region ORDER BY revenue DESC
    """).df().to_string(index=False))

    # 3) Window function: each order's share of its customer's total spend, and
    #    rank within customer. (Doable in Pandas, but far cleaner in SQL.)
    print("\n# 3. Window function over the DataFrame (top 5 rows)")
    print(con.execute("""
        SELECT order_id, customer_id, amount,
               round(100.0 * amount / sum(amount) OVER (PARTITION BY customer_id), 1) AS pct_of_cust,
               row_number() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rnk
        FROM orders
        ORDER BY customer_id, rnk
        LIMIT 5
    """).df().to_string(index=False))

    # 4) Mix an in-memory DataFrame with a Parquet file on disk in ONE query.
    if os.path.exists(TAXI):
        print("\n# 4. DataFrame JOIN Parquet-on-disk in a single query")
        # Contrived but illustrative: bucket orders by hour, join to taxi trip
        # counts by pickup hour -- two totally different sources, one SQL join.
        print(con.execute(f"""
            WITH taxi_by_hr AS (
                SELECT hour(tpep_pickup_datetime) AS hr, count(*) AS trips
                FROM read_parquet('{TAXI}')
                WHERE fare_amount > 0 GROUP BY hr
            ),
            orders_by_hr AS (
                SELECT hour(ts) AS hr, count(*) AS orders FROM orders GROUP BY hr
            )
            SELECT o.hr, o.orders, t.trips
            FROM orders_by_hr o JOIN taxi_by_hr t USING (hr)
            ORDER BY o.hr LIMIT 6
        """).df().to_string(index=False))
    else:
        print(f"\n# 4. (skipped -- {TAXI} not present; run ../01_nyc_taxi/get_data.sh)")

    # 5) Result also comes back as Arrow with zero conversion cost.
    reader = con.execute("SELECT count(*) AS n, round(avg(amount),2) AS avg_amt FROM orders").arrow()
    tbl = reader.read_all() if hasattr(reader, "read_all") else reader
    print(f"\n# 5. Same engine, result as Arrow: {tbl.to_pydict()}")

    print("\nDone -- SQL and Pandas over the same in-memory buffers, no copies.")


if __name__ == "__main__":
    main()
