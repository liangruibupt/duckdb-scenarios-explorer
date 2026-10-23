"""Scenario 11 -- DuckDB-on-Glue ETL to a managed Iceberg table (offline, via
DuckLake). Invariants: the transform cleans/casts (subtractive), each job run is
its own snapshot, and the table is time-travellable to the end of run 1."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
S11 = REPO / "scenarios" / "11_glue_duckdb_etl"


def _mod():
    spec = importlib.util.spec_from_file_location("s11", S11 / "glue_etl.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _two_runs(tmp_path):
    import datetime as dt
    m = _mod()
    con = m.connect_ducklake(str(tmp_path))
    raw1 = str(tmp_path / "d1.csv")
    raw2 = str(tmp_path / "d2.csv")
    m.make_raw_drop(raw1, dt.date(2026, 10, 20), n=10_000)
    m.make_raw_drop(raw2, dt.date(2026, 10, 21), n=10_000)
    m.run_job(con, raw1, first=True)
    snap1 = max(m.snapshots(con))
    n1 = con.execute("SELECT count(*) FROM sales").fetchone()[0]
    m.run_job(con, raw2, first=False)
    snap2 = max(m.snapshots(con))
    n2 = con.execute("SELECT count(*) FROM sales").fetchone()[0]
    return m, con, snap1, snap2, n1, n2


def test_transform_is_subtractive(tmp_path):
    """Bad units (-1), blank store and unparsable rows are dropped, so the clean
    count is below the raw row count."""
    import datetime as dt
    m = _mod()
    con = m.connect_ducklake(str(tmp_path))
    raw = str(tmp_path / "d.csv")
    m.make_raw_drop(raw, dt.date(2026, 10, 20), n=10_000)
    clean = con.execute(f"SELECT count(*) FROM ({m.transform_sql(raw)})").fetchone()[0]
    assert 0 < clean < 10_000


def test_every_clean_row_valid(tmp_path):
    m, con, *_ = _two_runs(tmp_path)
    bad = con.execute("""SELECT count(*) FROM sales
        WHERE units <= 0 OR store IS NULL OR unit_price IS NULL OR ts IS NULL
    """).fetchone()[0]
    assert bad == 0


def test_revenue_is_units_times_price(tmp_path):
    m, con, *_ = _two_runs(tmp_path)
    mismatch = con.execute("""SELECT count(*) FROM sales
        WHERE abs(revenue - round(units * unit_price, 2)) > 0.01""").fetchone()[0]
    assert mismatch == 0


def test_each_run_is_a_snapshot(tmp_path):
    m, con, snap1, snap2, n1, n2 = _two_runs(tmp_path)
    assert snap2 > snap1                 # a new snapshot per append
    assert n2 > n1                       # table grew on the second run


def test_time_travel_to_run_one(tmp_path):
    m, con, snap1, snap2, n1, n2 = _two_runs(tmp_path)
    at1 = con.execute(f"SELECT count(*) FROM sales AT (VERSION => {snap1})").fetchone()[0]
    assert at1 == n1                     # AS OF run 1 == day-1 rows only
    assert at1 < n2


def test_store_and_category_normalized(tmp_path):
    """The transform lowercases + trims store/category, so no mixed-case or
    whitespace-padded values survive."""
    m, con, *_ = _two_runs(tmp_path)
    dirty = con.execute("""SELECT count(*) FROM sales
        WHERE store <> lower(trim(store)) OR category <> lower(trim(category))
    """).fetchone()[0]
    assert dirty == 0
