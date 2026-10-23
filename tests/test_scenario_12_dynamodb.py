"""Scenario 12 -- DynamoDB zero-ETL to Iceberg, DuckDB analytics (offline). The
load-bearing invariant is the zero-ETL FLATTENING: DynamoDB type descriptors are
unwrapped to native typed values and attribute names are lowercased, so the
landed table is plain typed rows (PK -> pk, {"N":..} -> numeric)."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
S12 = REPO / "scenarios" / "12_dynamodb_zero_etl"


def _mod():
    spec = importlib.util.spec_from_file_location("s12", S12 / "ddb_analytics.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_synth_items_are_wrapped():
    m = _mod()
    items = m.synth_dynamodb_items(50)
    assert len(items) == 50
    for it in items:
        for name, desc in it.items():
            assert isinstance(desc, dict) and len(desc) == 1   # one type descriptor
            (typ,), = [tuple(desc.keys())]
            assert typ in {"S", "N"}


def test_flatten_unwraps_and_lowercases():
    m = _mod()
    rows = m.zero_etl_flatten(m.synth_dynamodb_items(100))
    for r in rows:
        # names lowercased: PK -> pk, SK -> sk, never the upper form
        assert "pk" in r and "PK" not in r
        assert "sk" in r and "SK" not in r
        # amount unwrapped to a real number, not a {"N": "..."} dict or string
        assert isinstance(r["amount"], (int, float))
        assert isinstance(r["items"], int)             # integral N -> int
        assert isinstance(r["category"], str)


def test_numeric_descriptor_becomes_number():
    m = _mod()
    one = [{"PK": {"S": "C#1"}, "SK": {"S": "O#1"}, "order_id": {"S": "1"},
            "category": {"S": "toys"}, "status": {"S": "placed"},
            "amount": {"N": "187.20"}, "items": {"N": "3"}}]
    r = m.zero_etl_flatten(one)[0]
    assert r["amount"] == 187.20
    assert r["items"] == 3 and isinstance(r["items"], int)


def _landed(tmp_path):
    m = _mod()
    con = m.connect_ducklake(str(tmp_path))
    rows = m.zero_etl_flatten(m.synth_dynamodb_items(2_000))
    m.land_orders(con, rows)
    return m, con


def test_landed_table_is_typed(tmp_path):
    m, con = _landed(tmp_path)
    types = {r[0]: r[1] for r in
             con.execute("DESCRIBE orders").fetchall()}
    assert types["amount"] in ("DOUBLE", "FLOAT", "DECIMAL")
    assert types["items"] in ("INTEGER", "BIGINT")
    assert types["category"] == "VARCHAR"


def test_revenue_by_category_sums(tmp_path):
    m, con = _landed(tmp_path)
    df = con.execute("""SELECT category, round(sum(amount),2) revenue
        FROM orders GROUP BY category ORDER BY revenue DESC""").fetchdf()
    assert len(df) == len(m.CATEGORIES)
    # the per-category revenues must sum to the table total (no rows dropped)
    total = con.execute("SELECT round(sum(amount),2) FROM orders").fetchone()[0]
    assert abs(float(df["revenue"].sum()) - float(total)) < 1.0


def test_analytical_query_does_not_touch_descriptors(tmp_path):
    """A query against the landed table uses plain columns -- no attribute
    unwrapping in SQL (the whole point of the flattening)."""
    m, con = _landed(tmp_path)
    n = con.execute("SELECT count(*) FROM orders WHERE amount > 0").fetchone()[0]
    assert n > 0
