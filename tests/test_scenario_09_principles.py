"""Scenario 09 -- principles, CoW/MoR, pruning demos (offline, ducklake-gated)."""
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
    not _ducklake_available(), reason="ducklake extension unavailable")

BASE = pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "09_iceberg"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --- principles --------------------------------------------------------------

def test_principles_all_four():
    p = _load("principles")
    with tempfile.TemporaryDirectory() as tmp:
        r = p.demo(p._lake(tmp))
    # (1) time-travel: current mutated, history preserved
    assert r["p1_current_id2"] == 999 and r["p1_asof_id2"] == 200
    # (2) schema evolution: added column absent in old snapshot
    assert r["p2_current_cols"] == 4 and r["p2_asof_cols"] == 3
    # (3) pruning: filter pushed, correct subset
    assert r["p3_plan_has_filter"] and r["p3_pruned_rows"] == 10_000
    # (4) row-level MoR delete: delete file added, data files unchanged, row gone
    assert r["p4_is_mor"] and r["p4_row_gone"]


# --- copy-on-write vs merge-on-read -----------------------------------------

def test_cow_vs_mor_signatures():
    m = _load("cow_vs_mor")
    with tempfile.TemporaryDirectory() as tmp:
        r = m.demo(m._lake(tmp))
    # MoR delete: a delete file appears, data files not rewritten
    assert r["mor_after_delete"]["delete_files"] > r["base"]["delete_files"]
    assert r["mor_after_delete"]["data_files"] == r["base"]["data_files"]
    # CoW rewrite: fresh data files, no delete file
    assert r["cow_rewrite"]["delete_files"] == 0
    assert r["rows_after"] < 50_000


# --- pruning benchmark (smoke: it runs and prunes correctly) -----------------

def test_pruning_benchmark_runs():
    # the module runs end-to-end in main(); here we just assert the ducklake
    # prune returns the right count for the selective day (2000 rows/day)
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect()
        con.execute(f"""COPY (SELECT (i%2000) id,
            DATE '2024-01-01' + (i//2000)::INT AS dt, (i%100)*1.0 amt
            FROM range(20*2000) t(i))
            TO '{tmp}/pq' (FORMAT parquet, PARTITION_BY (dt), OVERWRITE_OR_IGNORE true)""")
        con.execute("INSTALL ducklake; LOAD ducklake;")
        con.execute(f"ATTACH 'ducklake:{tmp}/c.ducklake' AS lake (DATA_PATH '{tmp}/ld')")
        con.execute("USE lake")
        con.execute(f"CREATE TABLE ev AS SELECT * FROM read_parquet('{tmp}/pq/**/*.parquet', hive_partitioning=true)")
        n = con.execute("SELECT count(*) FROM ev WHERE dt = DATE '2024-01-05'").fetchone()[0]
        assert n == 2000
