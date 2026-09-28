"""Scenario 08 governance layer — RLS/CLS/allow-list/shape invariants (offline).

Includes a persona × table × statement-shape matrix whose expected outcome is
derived from the policy, mirroring the aws-samples governance-matrix approach.
"""
import importlib.util
import pathlib
import pytest

MOD = (pathlib.Path(__file__).resolve().parents[1]
       / "scenarios" / "08_governance" / "data_agent" / "governance.py")


def _load():
    import sys
    spec = importlib.util.spec_from_file_location("governance", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules["governance"] = m          # dataclass type resolution needs this
    spec.loader.exec_module(m)
    return m


g = _load()

# policies: admin (unrestricted), analyst (RLS+CLS), junior (extra CLS)
POLICIES = {
    "acme:admin": g.Policy(unrestricted=True),
    "acme:analyst": g.Policy(tables={
        "trips": g.TablePolicy(row_filter="payment_type = 1",
                               deny_columns=("tip_amount",)),
    }),
    "acme:junior": g.Policy(tables={
        "trips": g.TablePolicy(row_filter="payment_type = 1",
                               deny_columns=("tip_amount", "fare_amount")),
    }),
}


# --- fail-closed floor -------------------------------------------------------

def test_missing_principal_is_deny_all():
    assert g.resolve_policy(POLICIES, None, None) is g.DENY_ALL
    assert g.resolve_policy(POLICIES, "acme", "ghost") is g.DENY_ALL


def test_deny_all_refuses_every_table():
    with pytest.raises(g.GovernanceError):
        g.govern("SELECT * FROM trips", g.DENY_ALL)


# --- RLS / CLS ---------------------------------------------------------------

def test_rls_anded_into_where():
    out = g.govern("SELECT fare_amount FROM trips WHERE trip_distance > 2",
                   POLICIES["acme:analyst"])
    assert "payment_type = 1" in out and "trip_distance > 2" in out


def test_rls_added_when_no_where():
    out = g.govern("SELECT count(*) FROM trips", POLICIES["acme:analyst"])
    assert "WHERE payment_type = 1" in out


def test_cls_excludes_denied_from_star():
    out = g.govern("SELECT * FROM trips", POLICIES["acme:analyst"])
    assert "EXCLUDE" in out and "tip_amount" in out


def test_cls_named_denied_column_refused():
    with pytest.raises(g.GovernanceError) as e:
        g.govern("SELECT tip_amount FROM trips", POLICIES["acme:analyst"])
    assert "tip_amount" in str(e.value)


# --- allow-list / shape / shadow / host --------------------------------------

def test_unlisted_table_refused():
    with pytest.raises(g.GovernanceError):
        g.govern("SELECT * FROM secret", POLICIES["acme:analyst"])


def test_dml_refused_even_behind_cte():
    with pytest.raises(g.GovernanceError):
        g.govern("WITH x AS (SELECT 1) DELETE FROM trips", POLICIES["acme:analyst"])


def test_cte_cannot_shadow_governed_table():
    with pytest.raises(g.GovernanceError):
        g.govern("WITH trips AS (SELECT 1 AS payment_type) SELECT * FROM trips",
                 POLICIES["acme:analyst"])


def test_host_reaching_path_refused_for_admin_too():
    with pytest.raises(g.GovernanceError):
        g.govern("SELECT * FROM read_csv('/etc/passwd')", POLICIES["acme:admin"])


def test_admin_passes_unchanged_shape():
    out = g.govern("SELECT tip_amount FROM trips", POLICIES["acme:admin"])
    assert "tip_amount" in out and "EXCLUDE" not in out


# --- persona × shape matrix (outcome derived from policy) --------------------

SHAPES = {
    "plain": "SELECT {col} FROM trips",
    "cte": "WITH c AS (SELECT {col} FROM trips) SELECT * FROM c",
    "union": "SELECT {col} FROM trips UNION SELECT {col} FROM trips",
    "derived": "SELECT * FROM (SELECT {col} FROM trips) d",
}


@pytest.mark.parametrize("persona", ["acme:admin", "acme:analyst", "acme:junior"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_matrix_allowed_column(persona, shape):
    """fare_amount: allowed for admin+analyst, denied for junior."""
    sql = SHAPES[shape].format(col="fare_amount")
    pol = POLICIES[persona]
    if persona == "acme:junior":
        with pytest.raises(g.GovernanceError):
            g.govern(sql, pol)
    else:
        out = g.govern(sql, pol)
        assert "trips" in out
        if persona == "acme:analyst":
            assert "payment_type = 1" in out   # RLS applied on every shape


@pytest.mark.parametrize("persona", ["acme:analyst", "acme:junior"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_matrix_denied_column_refused_every_shape(persona, shape):
    sql = SHAPES[shape].format(col="tip_amount")
    with pytest.raises(g.GovernanceError):
        g.govern(sql, POLICIES[persona])
