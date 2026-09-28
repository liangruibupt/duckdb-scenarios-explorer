"""Scenario 09 -- Iceberg/DuckLake table differentiators (offline)."""
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

MOD = (pathlib.Path(__file__).resolve().parents[1]
       / "scenarios" / "09_iceberg" / "tables.py")


def _load():
    spec = importlib.util.spec_from_file_location("iceberg_tables", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


t = _load()


@pytest.fixture()
def result():
    with tempfile.TemporaryDirectory() as tmp:
        con = t.connect(tmp)
        yield t.demo(con)


def test_time_travel_shows_pre_update_state(result):
    as_of = {r[0]: r[2] for r in result["as_of_initial"]}   # id -> amount
    cur = {r[0]: r[2] for r in result["current"]}
    assert as_of[2] == 200          # before update
    assert cur[2] == 999            # after update


def test_row_level_delete_removed_a_row(result):
    as_of_ids = {r[0] for r in result["as_of_initial"]}
    cur_ids = {r[0] for r in result["current"]}
    assert 3 in as_of_ids and 3 not in cur_ids     # id3 deleted


def test_schema_evolution_added_column(result):
    # current rows have 4 fields (priority added); as-of rows have 3
    assert all(len(r) == 4 for r in result["current"])
    assert all(len(r) == 3 for r in result["as_of_initial"])
    # the new row carries the evolved column value
    new = [r for r in result["current"] if r[0] == 4][0]
    assert new[3] == "high"


def test_snapshots_grow_per_commit(result):
    # create + insert + update + delete + alter + insert => multiple snapshots
    assert len(result["snapshots"]) >= 5
    assert result["snapshots"] == sorted(result["snapshots"])
