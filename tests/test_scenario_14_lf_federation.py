"""Scenario 14 -- Lake Formation as the policy source + lake/non-lake join (offline).

Load-bearing invariants:
  * Lake Formation grants compile to scenario 08 policies with LF's semantics:
    SELECT only, data-cell filters become row filters, column scopes become
    deny-lists, multiple grants union, and anything unclear is dropped (fail-closed).
  * External rows enter the session only through a registered tool, scoped to the
    caller's tenant, as an owner-bound handle; the join is governed like any query.
"""
import copy
import importlib.util
import json
import pathlib
import sys

import duckdb
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
S14 = REPO / "scenarios" / "14_lf_governance_federation"
SNAP = json.loads((S14 / "fixtures" / "lf_snapshot.json").read_text())
ACME = "arn:aws:iam::111122223333:role/acme-analyst"


def _mod(name):
    # keep S14 on sys.path: demo.py imports federation / lf_policy by name
    if str(S14) not in sys.path:
        sys.path.insert(0, str(S14))
    spec = importlib.util.spec_from_file_location(f"s14_{name}", S14 / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m          # @dataclass looks the module up here
    spec.loader.exec_module(m)
    return m


lf = _mod("lf_policy")
demo = _mod("demo")
fed = demo.fed


def policies(snap=SNAP):
    return lf.policies_from_lf(snap, snap["principal_map"])


# --- Lake Formation -> policy ----------------------------------------------

def test_cell_filter_becomes_row_filter_and_column_deny():
    tp = policies()["acme:analyst"].tables["orders"]
    assert tp.row_filter == "(tenant = 'acme')"
    assert tp.deny_columns == ("card_number",)


def test_column_allow_list_becomes_deny_list():
    tp = policies()["acme:analyst"].tables["refunds"]
    assert tp.row_filter is None
    assert tp.deny_columns == ("reason",)


def test_table_wildcard_grants_every_table_in_database():
    pol = policies()["acme:auditor"]
    assert set(pol.tables) == {"orders", "refunds"}
    assert all(t.row_filter is None and not t.deny_columns for t in pol.tables.values())


def test_describe_only_and_unmapped_principals_get_nothing():
    p = policies()
    assert "acme:viewer" not in p
    assert "initech:analyst" not in p


def test_multiple_grants_union_rows_and_columns():
    snap = copy.deepcopy(SNAP)
    snap["permissions"].append({
        "Principal": {"DataLakePrincipalIdentifier": ACME},
        "Resource": {"DataCellsFilter": {"DatabaseName": "sales", "TableName": "orders",
                                         "Name": "globex_rows_no_card"}},
        "Permissions": ["SELECT"]})
    tp = policies(snap)["acme:analyst"].tables["orders"]
    assert tp.row_filter == "(tenant = 'acme') OR (tenant = 'globex')"


def test_unparseable_or_missing_filter_drops_table():
    snap = copy.deepcopy(SNAP)
    snap["cell_filters"][0]["RowFilter"] = {"FilterExpression": "tenant = = 'acme' ))"}
    assert "orders" not in policies(snap)["acme:analyst"].tables
    snap = copy.deepcopy(SNAP)
    snap["cell_filters"] = [f for f in snap["cell_filters"] if f["Name"] != "acme_rows_no_card"]
    assert "orders" not in policies(snap)["acme:analyst"].tables


def test_grant_on_unknown_table_is_ignored():
    snap = copy.deepcopy(SNAP)
    snap["permissions"].append({
        "Principal": {"DataLakePrincipalIdentifier": ACME},
        "Resource": {"Table": {"DatabaseName": "sales", "Name": "salaries"}},
        "Permissions": ["SELECT"]})
    assert "salaries" not in policies(snap)["acme:analyst"].tables


# --- federation + governed join --------------------------------------------

@pytest.fixture()
def lake(tmp_path):
    con = duckdb.connect()
    demo.build_lake(con, tmp_path)
    crm = demo.build_crm()
    yield con, crm
    con.close()


def test_tool_rows_are_scoped_to_session_tenant(lake):
    con, crm = lake
    s = demo.session(SNAP, "acme", "analyst", con, crm)
    h = s.call_tool("crm_accounts")
    names = {r[0] for r in s.query(f"SELECT account_name FROM {h}")["rows"]}
    assert names == {"Acme Retail", "Acme Online", "Acme Wholesale"}


def test_model_cannot_choose_tenant_or_unknown_args(lake):
    con, crm = lake
    s = demo.session(SNAP, "acme", "analyst", con, crm)
    with pytest.raises(fed.FederationError):
        s.call_tool("crm_accounts", tenant="globex")
    with pytest.raises(fed.FederationError):
        s.call_tool("crm_accounts", sql="SELECT * FROM accounts")
    with pytest.raises(fed.FederationError):
        s.call_tool("hr_salaries")


def test_tool_allow_list(lake):
    con, crm = lake
    with pytest.raises(fed.FederationError):
        demo.session(SNAP, "acme", "viewer", con, crm).call_tool("crm_accounts")


def test_join_applies_lake_row_filter(lake):
    con, crm = lake
    s = demo.session(SNAP, "acme", "analyst", con, crm)
    h = s.call_tool("crm_accounts")
    r = s.query(demo.JOIN_SQL.format(h=h))
    assert "tenant = 'acme'" in r["governed_sql"]
    total = sum(row[2] for row in r["rows"])
    expected = con.execute("SELECT count(*) FROM sales.orders WHERE tenant = 'acme'").fetchone()[0]
    assert total == expected


def test_foreign_handle_refused(lake):
    con, crm = lake
    acme = demo.session(SNAP, "acme", "analyst", con, crm)
    globex = demo.session(SNAP, "globex", "analyst", con, crm)
    hg = globex.call_tool("crm_accounts")
    with pytest.raises(fed.FederationError):
        acme.query(f"SELECT * FROM {hg}")


def test_star_excludes_denied_columns_in_subqueries_and_ctes(lake):
    con, crm = lake
    s = demo.session(SNAP, "acme", "analyst", con, crm)
    for sql in ["SELECT * FROM orders LIMIT 5",
                "SELECT * FROM (SELECT * FROM orders) t LIMIT 5",
                "WITH x AS (SELECT * FROM orders) SELECT * FROM x LIMIT 5",
                "SELECT * FROM refunds LIMIT 5"]:
        cols = s.query(sql)["columns"]
        assert "card_number" not in cols and "reason" not in cols, sql
    from data_agent.governance import GovernanceError
    with pytest.raises(GovernanceError):
        s.query("SELECT * FROM (SELECT card_number FROM orders) t")


def test_demo_runs_end_to_end(lake):
    con, crm = lake
    log = "\n".join(demo.run(SNAP, con, crm))
    assert "NOT refused" not in log
    assert log.count("refused ->") == 6
