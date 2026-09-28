"""Scenario 08 pipeline + semantic layer — end-to-end wiring (offline)."""
import importlib
import pathlib
import sys
import pytest
import duckdb

ROOT = (pathlib.Path(__file__).resolve().parents[1]
        / "scenarios" / "08_governance")


@pytest.fixture(scope="module")
def da():
    sys.path.insert(0, str(ROOT))
    import data_agent
    from data_agent import governance, context, pipeline, semantic
    return governance, context, pipeline, semantic


@pytest.fixture()
def env(da):
    gov, ctx, pl, sem = da
    con = duckdb.connect()
    con.execute("""CREATE TABLE trips AS
        SELECT (i%3)+1 AS payment_type, (i%24) AS hr, i*1.0 AS fare_amount,
               i*0.1 AS tip_amount, '2024-01-01' AS dt
        FROM range(500) t(i)""")
    policies = {
        "acme:analyst": gov.Policy(tables={
            "trips": gov.TablePolicy(row_filter="payment_type = 1",
                                     deny_columns=("tip_amount",))}),
        "acme:admin": gov.Policy(unrestricted=True),
    }
    store = ctx.ResultStore(con, owner="acme:analyst", max_rows=200)
    return gov, ctx, pl, sem, con, policies, store


# --- pipeline ----------------------------------------------------------------

def test_pipeline_applies_rls_then_executes(env):
    gov, ctx, pl, sem, con, policies, store = env
    out = pl.run_statement("SELECT count(*) AS n FROM trips", "acme", "analyst",
                           policies=policies, partitioned={}, store=store)
    assert "result" in out
    assert out["audit"].ok and out["audit"].rls_applied
    # RLS payment_type=1 => count is the filtered subset, not all 500
    n = out["result"]["rows"][0][0]
    full = con.execute("SELECT count(*) FROM trips").fetchone()[0]
    assert 0 < n < full


def test_pipeline_refuses_denied_column_at_govern(env):
    gov, ctx, pl, sem, con, policies, store = env
    out = pl.run_statement("SELECT tip_amount FROM trips", "acme", "analyst",
                           policies=policies, partitioned={}, store=store)
    assert out["refused"]["stage"] == "govern"
    assert "tip_amount" in out["refused"]["error"]


def test_pipeline_cost_gate_sees_governed_sql(env):
    gov, ctx, pl, sem, con, policies, store = env
    # trips partitioned on dt; a query with no dt predicate is refused at cost,
    # AFTER govern (proving order govern->cost)
    out = pl.run_statement("SELECT count(*) AS n FROM trips", "acme", "analyst",
                           policies=policies, partitioned={"trips": "dt"},
                           store=store)
    assert out["refused"]["stage"] == "cost"


def test_pipeline_anonymous_is_deny_all(env):
    gov, ctx, pl, sem, con, policies, store = env
    out = pl.run_statement("SELECT * FROM trips", None, None,
                           policies=policies, partitioned={}, store=store)
    assert out["refused"]["stage"] == "govern"


# --- semantic ----------------------------------------------------------------

@pytest.fixture()
def registry(da):
    gov, ctx, pl, sem = da
    return sem.Registry([
        sem.Metric(name="trip_count", table="trips", agg="count(*)",
                   dimensions=("hr", "payment_type"), time_column="dt"),
    ])


def test_semantic_unregistered_metric_refused(da, registry):
    gov, ctx, pl, sem = da
    with pytest.raises(sem.SemanticError):
        registry.compile("revenue_forever")


def test_semantic_dimension_injection_refused(da, registry):
    gov, ctx, pl, sem = da
    with pytest.raises(sem.SemanticError) as e:
        registry.compile("trip_count", dimensions=("hr", "tip_amount"))
    assert "tip_amount" in str(e.value)


def test_semantic_compile_is_deterministic(da, registry):
    gov, ctx, pl, sem = da
    a = registry.compile("trip_count", dimensions=("hr",))
    b = registry.compile("trip_count", dimensions=("hr",))
    assert a == b and a.startswith("SELECT") and "GROUP BY hr" in a


def test_semantic_call_runs_through_governed_pipeline(env, da):
    gov, ctx, pl, sem, con, policies, store = env
    reg = sem.Registry([sem.Metric(name="trip_count", table="trips",
                                    agg="count(*)", dimensions=("hr",),
                                    time_column="dt")])
    out = sem.call_metric(reg, "trip_count", "acme", "analyst",
                          policies=policies, partitioned={}, store=store,
                          dimensions=("hr",))
    # RLS must still apply to a metric call
    assert out["audit"].rls_applied
    assert "result" in out
