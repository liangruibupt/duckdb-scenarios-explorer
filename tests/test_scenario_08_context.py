"""Scenario 08 context layer — cost gate, result handles, history compression (offline)."""
import importlib.util
import pathlib
import pytest
import duckdb

MOD = (pathlib.Path(__file__).resolve().parents[1]
       / "scenarios" / "08_governance" / "data_agent" / "context.py")


def _load():
    import sys
    spec = importlib.util.spec_from_file_location("context", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules["context"] = m             # dataclass type resolution needs this
    spec.loader.exec_module(m)
    return m


c = _load()
PARTS = {"trips": "dt"}


# --- cost gate ---------------------------------------------------------------

def test_unpartitioned_scan_refused():
    with pytest.raises(c.CostError) as e:
        c.cost_gate("SELECT * FROM trips", PARTS)
    assert "dt" in str(e.value)


def test_predicate_on_partition_accepted():
    c.cost_gate("SELECT * FROM trips WHERE dt = '2024-01-01'", PARTS)  # no raise


def test_rls_predicate_does_not_remove_partition_filter():
    # RLS ANDs payment_type; the dt predicate is still present => still accepted
    c.cost_gate("SELECT * FROM trips WHERE dt = '2024-01-01' AND payment_type = 1",
                PARTS)


def test_over_wide_partition_span_refused():
    days = ", ".join(f"'2024-01-{d:02d}'" for d in range(1, 3))  # small
    c.cost_gate(f"SELECT * FROM trips WHERE dt IN ({days})", PARTS, max_partitions=366)
    big = ", ".join(f"'{i}'" for i in range(400))
    with pytest.raises(c.CostError):
        c.cost_gate(f"SELECT * FROM trips WHERE dt IN ({big})", PARTS, max_partitions=366)


# --- result handles ----------------------------------------------------------

@pytest.fixture()
def store():
    con = duckdb.connect()
    con.execute("CREATE TABLE big AS SELECT range AS i FROM range(1000)")
    con.execute("CREATE TABLE small AS SELECT range AS i FROM range(10)")
    return c.ResultStore(con, owner="alice", max_rows=200)


def test_small_result_inline(store):
    r = store.run("SELECT * FROM small")
    assert r["handle"] is None and r["row_count"] == 10
    assert len(r["rows"]) == 10


def test_large_result_materialized_as_handle(store):
    r = store.run("SELECT * FROM big")
    assert r["handle"] == "_r_1" and r["row_count"] == 1000
    assert len(r["samples"]) == 3
    assert "rows" not in r                      # not truncated head


def test_handle_readback(store):
    r = store.run("SELECT * FROM big")
    rows = store.read_handle(r["handle"], r["retrieval"])
    assert len(rows) == 1000


def test_foreign_handle_refused(store):
    with pytest.raises(c.HandleError):
        store.read_handle("_r_99", "SELECT * FROM _r_99")


# --- history compression -----------------------------------------------------

def _msgs(n_big=4):
    msgs = [c.Message("system", "prompt", 50)]
    for i in range(n_big):
        msgs.append(c.Message("assistant", "X" * 4000, 1000, handle=f"_r_{i+1}"))
        msgs.append(c.Message("user", "next?", 10))
    return msgs


def test_no_compression_below_threshold():
    msgs = _msgs(n_big=1)                        # small usage
    out = c.compress_history(msgs, window_tokens=100_000)
    assert out == msgs


def test_old_result_blobs_stubbed_current_untouched():
    msgs = _msgs(n_big=4)                        # ~4040 tokens
    out = c.compress_history(msgs, window_tokens=6000, threshold=0.6)
    # last message untouched
    assert out[-1].content == msgs[-1].content
    # at least one earlier big result blob became a pointer stub
    stubbed = [m for m in out if m.content.startswith("[materialized result")]
    assert stubbed
    assert all("_r_" in m.content for m in stubbed)


def test_min_messages_guard():
    few = [c.Message("assistant", "X" * 4000, 5000, handle="_r_1")]
    out = c.compress_history(few, window_tokens=1000, min_messages=6)
    assert out == few                            # too few messages, no compression
