"""Scenario 05 -- SQL over Pandas DataFrames invariants (offline)."""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def frames():
    rng = np.random.default_rng(42)
    n = 20_000
    orders = pd.DataFrame({
        "order_id": np.arange(n),
        "customer_id": rng.integers(1, 1_000, n),
        "region_id": rng.integers(1, 6, n),
        "amount": rng.gamma(2.0, 50.0, n).round(2),
    })
    regions = pd.DataFrame({"region_id": [1, 2, 3, 4, 5],
                            "region": list("ABCDE")})
    return orders, regions


def test_dataframe_queryable_by_name(con, frames):
    orders, regions = frames
    n = con.execute("SELECT count(*) FROM orders").fetchone()[0]
    assert n == len(orders)


def test_df_join_df_loses_nothing(con, frames):
    orders, regions = frames
    joined = con.execute("""
        SELECT round(sum(o.amount),2) rev
        FROM orders o JOIN regions r USING (region_id)""").fetchone()[0]
    total = con.execute("SELECT round(sum(amount),2) FROM orders").fetchone()[0]
    assert abs(joined - total) < 1.0        # inner join covers all region_ids


def test_window_pct_sums_to_100_per_customer(con, frames):
    orders, regions = frames
    df = con.execute("""
        SELECT customer_id, sum(pct) total_pct FROM (
          SELECT customer_id,
                 100.0*amount/sum(amount) OVER (PARTITION BY customer_id) pct
          FROM orders)
        GROUP BY customer_id""").fetchdf()
    assert df.total_pct.between(99.9, 100.1).all()


def test_arrow_result_reads_back(con, frames):
    orders, regions = frames
    reader = con.execute(
        "SELECT count(*) n, round(avg(amount),2) a FROM orders").arrow()
    tbl = reader.read_all() if hasattr(reader, "read_all") else reader
    d = tbl.to_pydict()
    assert d["n"][0] == len(orders)
    assert d["a"][0] > 0
