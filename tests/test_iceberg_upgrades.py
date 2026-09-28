"""Iceberg/DuckLake upgrades to scenarios 03 (ETL) and 06 (logs) — offline."""
import importlib.util
import pathlib
import tempfile
import pytest
import duckdb


def _ducklake_available() -> bool:
    try:
        duckdb.connect().execute("INSTALL ducklake; LOAD ducklake;")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ducklake_available(),
    reason="ducklake extension unavailable (offline CI without the extension repo)")


def _load(rel, name):
    mod = pathlib.Path(__file__).resolve().parents[1] / "scenarios" / rel
    spec = importlib.util.spec_from_file_location(name, mod)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


etl = _load("03_csv_to_parquet_etl/etl.py", "etl_ice")
log = _load("06_log_analytics/log_analytics.py", "log_ice")


# --- 03 CSV -> managed DuckLake table ----------------------------------------

def test_etl_ducklake_two_appends_two_snapshots(tmp_path):
    raw = tmp_path / "raw.csv"
    etl.make_messy_csv(str(raw), n=10_000)
    r = etl.load_to_ducklake(str(raw), str(tmp_path))
    # each append advances the snapshot and adds rows
    assert r["snapshot_after_2"] > r["snapshot_after_1"]
    assert r["rows_after_2"] == 2 * r["rows_after_1"]
    # time-travel to the first snapshot sees only the first batch
    assert r["rows_at_v1"] == r["rows_after_1"]


# --- 06 logs -> time-travel across the spike ---------------------------------

def test_log_timetravel_pre_spike_snapshot_excludes_spike(tmp_path):
    p = tmp_path / "access.ndjson"
    log.make_log(str(p), n=40_000)
    r = log.load_to_ducklake_with_timetravel(str(p), str(tmp_path))
    # the pre-spike snapshot must contain ZERO rows in the spike window
    assert r["spike_minutes_in_pre_snapshot"] == 0
    # the current table's spike-window p95 is a real (positive) latency
    assert r["current_spike_p95"] and r["current_spike_p95"] > 0
