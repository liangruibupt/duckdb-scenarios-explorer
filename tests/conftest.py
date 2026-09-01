"""Shared fixtures + dependency gating for the scenario test suite.

Tiers (see specs/SPEC.md):
  offline      -> always run
  data-gated   -> skip if the taxi Parquet is absent
  s3-gated     -> skip unless RUN_S3_TESTS=1
"""
import os
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TAXI = REPO / "scenarios" / "01_nyc_taxi" / "data" / "yellow_2024-01.parquet"
ZONES = REPO / "scenarios" / "01_nyc_taxi" / "data" / "taxi_zone_lookup.csv"


def has_taxi() -> bool:
    return TAXI.exists() and ZONES.exists()


requires_taxi = pytest.mark.skipif(
    not has_taxi(),
    reason="taxi Parquet absent -- run scenarios/01_nyc_taxi/get_data.sh")

requires_s3 = pytest.mark.skipif(
    os.environ.get("RUN_S3_TESTS") != "1",
    reason="S3 tests off -- set RUN_S3_TESTS=1 (needs seeded bucket + creds)")


@pytest.fixture(scope="session")
def con():
    import duckdb
    c = duckdb.connect()
    yield c
    c.close()


@pytest.fixture(scope="session")
def taxi_path():
    return str(TAXI)


@pytest.fixture(scope="session")
def zones_path():
    return str(ZONES)
