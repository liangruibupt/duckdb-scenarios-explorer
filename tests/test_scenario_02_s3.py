"""Scenario 02 -- httpfs/S3 remote Parquet invariants (s3-gated).

Skipped unless RUN_S3_TESTS=1 and the bucket is seeded (seed_s3.sh / boto3).
"""
import pytest
from conftest import requires_s3

pytestmark = requires_s3

BUCKET = "cdh-ingest-demo"
PREFIX = "duckdb-demo/nyc_taxi"
GOOD = f"s3://{BUCKET}/{PREFIX}/**/*.parquet"      # matches year=/month=/part
BAD = f"s3://{BUCKET}/{PREFIX}/*/*.parquet"        # one level -> regression


@pytest.fixture(scope="module")
def s3con():
    import duckdb
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs;")
    c.execute("CREATE OR REPLACE SECRET s3 (TYPE s3, PROVIDER credential_chain, REGION 'us-east-1');")
    return c


def test_recursive_glob_matches(s3con):
    n = s3con.execute(f"SELECT count(*) FROM read_parquet('{GOOD}')").fetchone()[0]
    assert n > 0


def test_single_level_glob_is_the_regression(s3con):
    """The bug we fixed: single-level */ must NOT match the two-level layout."""
    with pytest.raises(Exception):
        s3con.execute(f"SELECT count(*) FROM read_parquet('{BAD}')").fetchone()


def test_hive_pruning_exposes_partition_cols(s3con):
    df = s3con.execute(f"""
        SELECT year, month, count(*) trips
        FROM read_parquet('{GOOD}', hive_partitioning=true)
        WHERE year=2024 GROUP BY year, month""").fetchdf()
    assert (df.year == 2024).all()
    assert len(df) >= 1
