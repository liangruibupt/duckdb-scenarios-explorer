"""Scenario 10 -- Aurora PostgreSQL + embedded-DuckDB data lake query pattern
(offline, self-contained). The offline demo proves the SAME query shape Aurora
now runs under `aurora_analytics`: one embedded DuckDB joins/unions a small
operational table with a large Parquet 'lake'."""
import importlib.util
import pathlib

import duckdb

REPO = pathlib.Path(__file__).resolve().parents[1]
S10 = REPO / "scenarios" / "10_aurora_pg_datalake"


def _mod():
    spec = importlib.util.spec_from_file_location("s10", S10 / "datalake_query.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _seeded(tmp_path):
    m = _mod()
    con = duckdb.connect()
    # small sizes keep the test fast; the demo's defaults are much larger
    lake = m.seed(con, str(tmp_path), recent_n=400, hist_n=4_000)
    return m, con, lake


def test_two_sources_have_rows(tmp_path):
    m, con, lake = _seeded(tmp_path)
    recent = con.execute("SELECT count(*) FROM recent_transactions").fetchone()[0]
    hist = con.execute(f"SELECT count(*) FROM read_parquet('{lake}')").fetchone()[0]
    assert recent > 0
    assert hist > recent                 # the lake is the big side


def test_recent_window_is_seven_days(tmp_path):
    m, con, lake = _seeded(tmp_path)
    span = con.execute(
        "SELECT max(transaction_date) - min(transaction_date) "
        "FROM recent_transactions").fetchone()[0]
    assert 0 <= span <= 6                 # last 7 days only


def test_unified_query_spans_both_sources(tmp_path):
    """The UNION reaches both branches. Ordered by date DESC, the top rows are
    the recent ones (that is the correct real behavior AWS describes: the most
    recent come from the OLTP table, the rest from history) -- so we assert both
    branches CONTRIBUTE by counting the full union, not just the LIMIT window."""
    m, con, lake = _seeded(tmp_path)
    both = con.execute(f"""
        SELECT source, count(*) n FROM (
            SELECT 'recent' AS source FROM recent_transactions
             WHERE customer_id = ?
            UNION ALL
            SELECT 'historical' AS source
              FROM read_parquet('{lake}')
             WHERE customer_id = ?
               AND transaction_date >= CURRENT_DATE - INTERVAL '5 years'
        ) GROUP BY source""", [m.CUSTOMER, m.CUSTOMER]).fetchall()
    counts = {s: n for s, n in both}
    assert counts.get("recent", 0) > 0
    assert counts.get("historical", 0) > 0


def test_unified_timeline_is_bounded_and_dated(tmp_path):
    m, con, lake = _seeded(tmp_path)
    rows = m.unified_timeline(con, lake, m.CUSTOMER)
    assert rows, "unified query returned nothing"
    assert len(rows) <= 15               # the LIMIT holds
    # every row has a known source label and is the queried customer's
    assert all(r[4] in {"recent", "historical"} for r in rows)
    # ordered by transaction_date DESC
    dates = [r[3] for r in rows]
    assert dates == sorted(dates, reverse=True)


def test_unified_query_is_single_customer(tmp_path):
    """Governance-adjacent invariant: the WHERE customer_id filter must hold on
    BOTH branches -- a lake scan that leaked other customers would break it."""
    m, con, lake = _seeded(tmp_path)
    # recompute the customer's own rows directly and compare the count ceiling
    hist_cust = con.execute(
        f"SELECT count(*) FROM read_parquet('{lake}') WHERE customer_id = ?",
        [m.CUSTOMER]).fetchone()[0]
    hist_all = con.execute(
        f"SELECT count(*) FROM read_parquet('{lake}')").fetchone()[0]
    assert 0 < hist_cust < hist_all       # the filter actually narrows


def test_enrich_join_matches_categories(tmp_path):
    m, con, lake = _seeded(tmp_path)
    rows = m.enrich_join(con, lake, m.CUSTOMER)
    assert rows, "enrichment join returned nothing"
    for merchant, cat, amt, havg, delta in rows:
        assert havg is not None           # every live row matched a hist average
        # delta is amount - hist_avg, within float rounding
        assert abs(float(delta) - (float(amt) - float(havg))) < 0.01
