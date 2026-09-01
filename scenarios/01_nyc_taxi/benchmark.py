#!/usr/bin/env python3
"""
DuckDB vs Pandas on the SAME analytical workload.

Workload: read the 3M-row taxi Parquet, filter to clean rows, group by pickup
hour, and compute count / avg fare / avg tip / total revenue.

Why DuckDB tends to win here:
  - Columnar + vectorized execution; only the touched columns are decoded.
  - Parquet projection/predicate push-down: it never materializes all 19 columns.
  - Pandas must read the whole file into memory (all columns) before grouping.
"""
from __future__ import annotations
import time
import duckdb
import pandas as pd

PARQUET = "data/yellow_2024-01.parquet"
REPEAT = 5

AGG_SQL = f"""
    SELECT hour(tpep_pickup_datetime) AS hr,
           count(*)          AS trips,
           avg(fare_amount)  AS avg_fare,
           avg(tip_amount)   AS avg_tip,
           sum(total_amount) AS revenue
    FROM read_parquet('{PARQUET}')
    WHERE trip_distance > 0 AND fare_amount > 0
    GROUP BY hr ORDER BY hr
"""


def bench(label: str, fn) -> float:
    best = float("inf")
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    print(f"  {label:28} best of {REPEAT}: {best * 1000:8,.1f} ms  ({len(out)} rows)")
    return best


def duckdb_run():
    return duckdb.connect().execute(AGG_SQL).fetchdf()


def pandas_run():
    # Pandas has to load the file first; group + aggregate in memory.
    df = pd.read_parquet(PARQUET,
                         columns=["tpep_pickup_datetime", "trip_distance",
                                  "fare_amount", "tip_amount", "total_amount"])
    df = df[(df.trip_distance > 0) & (df.fare_amount > 0)].copy()
    df["hr"] = df.tpep_pickup_datetime.dt.hour
    return (df.groupby("hr")
              .agg(trips=("hr", "size"),
                   avg_fare=("fare_amount", "mean"),
                   avg_tip=("tip_amount", "mean"),
                   revenue=("total_amount", "sum"))
              .reset_index())


def main() -> None:
    print(f"Benchmark: group-by-hour aggregate over {PARQUET}  (best of {REPEAT})\n")
    d = bench("DuckDB (SQL over Parquet)", duckdb_run)
    p = bench("Pandas (read_parquet+groupby)", pandas_run)
    faster = p / d if d else float("inf")
    print(f"\n  -> DuckDB is {faster:.1f}x faster on this workload "
          f"(and never materialized all 19 columns).")


if __name__ == "__main__":
    main()
