#!/usr/bin/env python3
"""
NYC Yellow Taxi analytics with DuckDB.

Demonstrates DuckDB's core strengths:
  - Query a 48MB / ~3M-row Parquet file directly, with NO load/import step.
  - Push-down projection + predicate filtering (only touched columns are read).
  - Rich SQL: window functions, percentiles (approx & exact), time bucketing,
    joins against a CSV dimension table -- all in one embedded engine.

Data (public, no auth):
  data/yellow_2024-01.parquet   NYC TLC yellow taxi trips, Jan 2024
  data/taxi_zone_lookup.csv     LocationID -> Borough / Zone dimension
"""
from __future__ import annotations
import time
import duckdb

TRIPS = "read_parquet('data/yellow_2024-01.parquet')"
ZONES = "read_csv('data/taxi_zone_lookup.csv')"


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def show(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    t0 = time.perf_counter()
    df = con.execute(sql).fetchdf()
    dt = (time.perf_counter() - t0) * 1000
    print(df.to_string(index=False))
    print(f"[{dt:,.1f} ms, {len(df)} rows]")


def main() -> None:
    con = duckdb.connect()  # in-process, in-memory

    # A cleaned CTE we reuse: drop obviously-bad rows (negative fares, zero-distance
    # long trips, absurd passenger counts) so aggregates aren't skewed.
    con.execute(f"""
        CREATE OR REPLACE VIEW clean AS
        SELECT *
        FROM {TRIPS}
        WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-01'
          AND tpep_pickup_datetime <  TIMESTAMP '2024-02-01'
          AND trip_distance > 0 AND trip_distance < 100
          AND fare_amount   > 0 AND fare_amount   < 500
          AND passenger_count BETWEEN 1 AND 6
          AND tpep_dropoff_datetime > tpep_pickup_datetime
    """)

    banner("0. Dataset overview (raw vs cleaned)")
    show(con, f"""
        SELECT
          (SELECT count(*) FROM {TRIPS})                            AS raw_rows,
          (SELECT count(*) FROM clean)                              AS clean_rows,
          (SELECT count(*) FROM {TRIPS}) - (SELECT count(*) FROM clean) AS dropped
    """)

    banner("1. Revenue & tipping by hour of day")
    show(con, """
        SELECT
          hour(tpep_pickup_datetime)                     AS hr,
          count(*)                                        AS trips,
          round(avg(fare_amount), 2)                      AS avg_fare,
          round(avg(tip_amount), 2)                       AS avg_tip,
          round(avg(tip_amount) / avg(fare_amount) * 100, 1) AS tip_pct,
          round(sum(total_amount), 0)                     AS revenue
        FROM clean
        GROUP BY hr
        ORDER BY hr
    """)

    banner("2. Trip-distance percentiles (exact + approx quantile)")
    show(con, """
        SELECT
          round(median(trip_distance), 2)                          AS p50,
          round(quantile_cont(trip_distance, 0.90), 2)             AS p90_exact,
          round(approx_quantile(trip_distance, 0.90), 2)           AS p90_approx,
          round(quantile_cont(trip_distance, 0.99), 2)             AS p99_exact,
          round(max(trip_distance), 2)                             AS max_dist
        FROM clean
    """)

    banner("3. Busiest pickup zones (join Parquet trips -> CSV zone dimension)")
    show(con, f"""
        SELECT
          z.Borough,
          z.Zone,
          count(*)                        AS trips,
          round(avg(c.total_amount), 2)   AS avg_total,
          round(sum(c.total_amount), 0)   AS revenue
        FROM clean c
        JOIN {ZONES} z ON c.PULocationID = z.LocationID
        GROUP BY z.Borough, z.Zone
        ORDER BY trips DESC
        LIMIT 10
    """)

    banner("4. Payment-type mix and tip behaviour")
    show(con, """
        SELECT
          CASE payment_type
            WHEN 1 THEN 'Credit card' WHEN 2 THEN 'Cash'
            WHEN 3 THEN 'No charge'   WHEN 4 THEN 'Dispute'
            ELSE 'Other' END                              AS payment,
          count(*)                                        AS trips,
          round(count(*) * 100.0 / sum(count(*)) OVER (), 1) AS pct_of_trips,
          round(avg(tip_amount), 2)                       AS avg_tip,
          round(100.0 * count_if(tip_amount > 0) / count(*), 1) AS pct_tipped
        FROM clean
        GROUP BY payment_type
        ORDER BY trips DESC
    """)

    banner("5. Daily trend with 7-day moving average (window function)")
    show(con, """
        WITH daily AS (
          SELECT tpep_pickup_datetime::DATE AS day, count(*) AS trips
          FROM clean GROUP BY day
        )
        SELECT
          day,
          trips,
          round(avg(trips) OVER (ORDER BY day
                 ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 0) AS ma7
        FROM daily
        ORDER BY day
    """)

    banner("6. Airport trips: JFK / LaGuardia / Newark share & economics")
    show(con, f"""
        SELECT
          z.Zone                                          AS airport,
          count(*)                                        AS trips,
          round(avg(c.trip_distance), 1)                  AS avg_miles,
          round(avg(c.total_amount), 2)                   AS avg_total,
          round(avg(c.tip_amount), 2)                     AS avg_tip
        FROM clean c
        JOIN {ZONES} z ON c.PULocationID = z.LocationID
        WHERE z.Zone ILIKE '%Airport%' OR z.Zone ILIKE '%LaGuardia%'
        GROUP BY z.Zone
        ORDER BY trips DESC
    """)

    print("\nDone.")


if __name__ == "__main__":
    main()
