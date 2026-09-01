"""Scenario 06 -- log analytics invariants (offline, self-contained)."""
import importlib.util
import pathlib
import pytest
import duckdb

REPO = pathlib.Path(__file__).resolve().parents[1]
S06 = REPO / "scenarios" / "06_log_analytics"


@pytest.fixture(scope="module")
def logs(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("la", S06 / "log_analytics.py")
    la = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(la)
    path = tmp_path_factory.mktemp("s06") / "access.ndjson"
    la.make_log(str(path), n=60_000)
    con = duckdb.connect()
    con.execute(f"""CREATE VIEW logs AS SELECT ts::TIMESTAMP ts, path,
        status::INT status, latency_ms::DOUBLE latency_ms
        FROM read_json_auto('{path}')""")
    return con


def test_line_count_matches(logs):
    assert logs.execute("SELECT count(*) FROM logs").fetchone()[0] == 60_000


def test_percentiles_monotonic_per_endpoint(logs):
    df = logs.execute("""
        SELECT path,
               approx_quantile(latency_ms,0.50) p50,
               approx_quantile(latency_ms,0.95) p95,
               approx_quantile(latency_ms,0.99) p99,
               max(latency_ms) mx
        FROM logs GROUP BY path""").fetchdf()
    assert (df.p50 <= df.p95).all()
    assert (df.p95 <= df.p99).all()
    assert (df.p99 <= df.mx).all()


def test_error_rate_within_bounds(logs):
    df = logs.execute("""
        SELECT path,
               100.0*count_if(status>=500)/count(*) pct5,
               100.0*count_if(status>=400 AND status<500)/count(*) pct4
        FROM logs GROUP BY path""").fetchdf()
    assert df.pct5.between(0, 100).all()
    assert df.pct4.between(0, 100).all()


def test_spike_minute_is_in_injected_window(logs):
    top = logs.execute("""
        SELECT time_bucket(INTERVAL '1 minute', ts) AS min_bucket,
               approx_quantile(latency_ms,0.95) p95
        FROM logs GROUP BY min_bucket ORDER BY p95 DESC LIMIT 1""").fetchone()[0]
    # injected spike is 14:10-14:13
    assert top.hour == 14 and 10 <= top.minute <= 13


def test_slo_summary_bounds(logs):
    row = logs.execute("""
        SELECT 100.0*count_if(status<400)/count(*) succ,
               approx_quantile(latency_ms,0.50) p50,
               approx_quantile(latency_ms,0.99) p99 FROM logs""").fetchone()
    assert 0 <= row[0] <= 100
    assert row[1] <= row[2]
