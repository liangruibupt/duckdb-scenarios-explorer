"""Scenario 03 -- CSV->Parquet ETL invariants (offline, self-contained)."""
import os
import pathlib
import duckdb

REPO = pathlib.Path(__file__).resolve().parents[1]
S03 = REPO / "scenarios" / "03_csv_to_parquet_etl"


def _run_etl(tmp_path):
    """Reproduce the ETL in an isolated tmp dir using the script's own
    CSV generator, so tests never touch the repo working tree."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("etl", S03 / "etl.py")
    etl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(etl)

    raw = tmp_path / "raw.csv"
    out = tmp_path / "out"
    etl.make_messy_csv(str(raw), n=20_000)
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW raw AS SELECT * FROM read_csv('{raw}', header=true,
          columns={{'event_id':'BIGINT','ts':'VARCHAR','category':'VARCHAR',
                    'region':'VARCHAR','amount':'VARCHAR','qty':'INTEGER'}},
          ignore_errors=true)""")
    con.execute("""
        CREATE VIEW clean AS SELECT event_id,
          try_cast(ts AS TIMESTAMP) ts, lower(trim(category)) category,
          nullif(lower(trim(region)),'') region,
          try_cast(replace(amount,',','') AS DECIMAL(10,2)) amount, qty
        FROM raw
        WHERE try_cast(ts AS TIMESTAMP) IS NOT NULL AND qty>0
          AND try_cast(replace(amount,',','') AS DECIMAL(10,2)) IS NOT NULL""")
    con.execute(f"""COPY (SELECT *, ts::DATE dt FROM clean) TO '{out}'
        (FORMAT parquet, PARTITION_BY (dt), COMPRESSION zstd, OVERWRITE_OR_IGNORE true)""")
    return con, raw, out


def test_cleaning_is_subtractive(tmp_path):
    con, raw, out = _run_etl(tmp_path)
    raw_n = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    clean_n = con.execute("SELECT count(*) FROM clean").fetchone()[0]
    assert 0 < clean_n < raw_n


def test_quoted_comma_amount_survives(tmp_path):
    """The regression: amount like 3,045.12 is quoted, so nearly all rows must
    survive -- not be dropped by the delimiter splitting the field."""
    con, raw, out = _run_etl(tmp_path)
    clean_n = con.execute("SELECT count(*) FROM clean").fetchone()[0]
    assert clean_n > 15_000           # ~80%+ survive, not near-zero


def test_every_clean_row_valid(tmp_path):
    con, raw, out = _run_etl(tmp_path)
    bad = con.execute("""SELECT count(*) FROM clean
        WHERE qty <= 0 OR ts IS NULL OR amount IS NULL""").fetchone()[0]
    assert bad == 0


def test_partitioned_output_roundtrips(tmp_path):
    con, raw, out = _run_etl(tmp_path)
    clean_n = con.execute("SELECT count(*) FROM clean").fetchone()[0]
    parts = con.execute(f"SELECT count(*) FROM glob('{out}/**/*.parquet')").fetchone()[0]
    rt = con.execute(f"SELECT count(*) FROM read_parquet('{out}/**/*.parquet')").fetchone()[0]
    assert parts >= 1
    assert rt == clean_n


def test_parquet_smaller_than_csv(tmp_path):
    con, raw, out = _run_etl(tmp_path)
    csv_sz = os.path.getsize(raw)
    pq_sz = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(out) for f in fs if f.endswith(".parquet"))
    assert 0 < pq_sz < csv_sz
