"""Scenario 01 -- NYC taxi analytics invariants (data-gated)."""
import pytest
from conftest import requires_taxi

pytestmark = requires_taxi


@pytest.fixture(scope="module")
def clean(con, taxi_path):
    con.execute(f"""
        CREATE OR REPLACE VIEW clean AS SELECT * FROM read_parquet('{taxi_path}')
        WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-01'
          AND tpep_pickup_datetime <  TIMESTAMP '2024-02-01'
          AND trip_distance>0 AND trip_distance<100
          AND fare_amount>0 AND fare_amount<500
          AND passenger_count BETWEEN 1 AND 6
          AND tpep_dropoff_datetime > tpep_pickup_datetime""")
    return con


def test_cleaning_subtractive(clean, taxi_path):
    raw = clean.execute(f"SELECT count(*) FROM read_parquet('{taxi_path}')").fetchone()[0]
    cl = clean.execute("SELECT count(*) FROM clean").fetchone()[0]
    assert 0 < cl < raw


def test_hourly_has_24_positive_buckets(clean):
    df = clean.execute("""
        SELECT hour(tpep_pickup_datetime) hr, count(*) trips
        FROM clean GROUP BY hr ORDER BY hr""").fetchdf()
    assert len(df) == 24
    assert (df.trips > 0).all()


def test_distance_percentiles_monotonic(clean):
    row = clean.execute("""
        SELECT median(trip_distance) p50,
               quantile_cont(trip_distance,0.90) p90,
               quantile_cont(trip_distance,0.99) p99,
               max(trip_distance) mx FROM clean""").fetchone()
    assert row[0] <= row[1] <= row[2] <= row[3]


def test_busiest_zones_bounded(clean, zones_path):
    df = clean.execute(f"""
        SELECT z.Borough, z.Zone, count(*) trips
        FROM clean c JOIN read_csv('{zones_path}') z ON c.PULocationID=z.LocationID
        GROUP BY z.Borough, z.Zone ORDER BY trips DESC LIMIT 10""").fetchdf()
    assert 0 < len(df) <= 10
    assert (df.trips > 0).all()
    assert df.Borough.notna().all()
