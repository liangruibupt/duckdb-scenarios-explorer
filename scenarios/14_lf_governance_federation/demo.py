#!/usr/bin/env python3
"""
Scenario 14 end to end (offline by default):

  Lake Formation snapshot -> policies -> governed SQL over a lake table
  + a registered tool call into a non-lake source -> join in one DuckDB session.

Offline, the "lake" is a DuckLake table (the repo's Iceberg-style stand-in) and
the non-lake source is a SQLite CRM database. With --s3tables-arn the lake is a
real Amazon S3 Tables bucket attached through its Iceberg REST endpoint; pass a
snapshot from fetch_lf.py with --snapshot to use your account's grants.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import tempfile

import duckdb

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import federation as fed  # noqa: E402
import lf_policy  # noqa: E402

FIXTURE = HERE / "fixtures" / "lf_snapshot.json"

TOOLS = {
    "crm_accounts": fed.Tool(
        name="crm_accounts",
        sql="SELECT account_id, account_name, segment FROM accounts "
            "WHERE tenant = :tenant AND (:segment IS NULL OR segment = :segment)",
        allowed_principals=frozenset({"acme:analyst", "globex:analyst"}),
        params=("segment",),
    ),
}


def build_crm() -> sqlite3.Connection:
    """The non-lake system: a CRM with accounts for several tenants."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE accounts (tenant TEXT, account_id INTEGER, "
               "account_name TEXT, segment TEXT)")
    db.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?)", [
        ("acme", 1, "Acme Retail", "enterprise"),
        ("acme", 2, "Acme Online", "smb"),
        ("acme", 3, "Acme Wholesale", "enterprise"),
        ("globex", 1, "Globex Corp", "enterprise"),
        ("globex", 2, "Globex Labs", "smb"),
    ])
    return db


def build_lake(con: duckdb.DuckDBPyConnection, root: pathlib.Path) -> None:
    """Offline lake: DuckLake catalog + Parquet, attached as `sales`."""
    con.execute("INSTALL ducklake; LOAD ducklake")
    con.execute(f"ATTACH 'ducklake:{(root / 'sales.ducklake').as_posix()}' AS sales "
                f"(DATA_PATH '{(root / 'data').as_posix()}/')")
    con.execute("""CREATE TABLE sales.orders AS
        SELECT i AS order_id,
               CASE WHEN i % 3 = 0 THEN 'globex' ELSE 'acme' END AS tenant,
               (i % 3) + 1 AS account_id,
               DATE '2026-10-01' + (i % 30)::INT AS order_date,
               round(10 + (i % 3) * 40 + (i % 11) * 1.5, 2) AS amount,
               '4111-0000-0000-' || lpad((i % 10000)::VARCHAR, 4, '0') AS card_number
        FROM range(3000) t(i)""")
    con.execute("""CREATE TABLE sales.refunds AS
        SELECT i AS refund_id, CASE WHEN i % 3 = 0 THEN 'globex' ELSE 'acme' END AS tenant,
               i * 10 AS order_id, 5.0 AS amount,
               'customer note ' || i AS reason FROM range(100) t(i)""")
    con.execute("USE sales")


def attach_s3tables(con: duckdb.DuckDBPyConnection, arn: str, region: str) -> None:
    """Real lake: S3 Tables bucket via its Iceberg REST endpoint (read-only)."""
    con.execute("INSTALL aws; INSTALL httpfs; INSTALL iceberg; "
                "LOAD aws; LOAD httpfs; LOAD iceberg")
    con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain)")
    con.execute(f"ATTACH '{arn}' AS sales (TYPE iceberg, ENDPOINT_TYPE s3_tables, "
                f"READ_ONLY)")
    con.execute("USE sales")


def session(snapshot: dict, tenant: str, role: str, con, crm) -> fed.FederatedSession:
    """One governed session with its own DuckDB connection (own temp tables)."""
    policies = lf_policy.policies_from_lf(snapshot, snapshot.get("principal_map", {}))
    cur = con.cursor()
    cur.execute("USE sales")
    return fed.FederatedSession(con=cur, tenant=tenant, role=role, policies=policies,
                                tools=TOOLS, external=crm)


JOIN_SQL = ("SELECT a.account_name, a.segment, count(*) AS orders, "
            "round(sum(o.amount), 2) AS revenue "
            "FROM orders o JOIN {h} a ON o.account_id = a.account_id "
            "GROUP BY ALL ORDER BY revenue DESC")


def run(snapshot: dict, con, crm) -> list[str]:
    log: list[str] = []
    p = log.append
    acme = session(snapshot, "acme", "analyst", con, crm)

    p("== Policies compiled from Lake Formation ==")
    for name, pol in sorted(acme.policies.items()):
        for t, tp in sorted(pol.tables.items()):
            p(f"  {name:15s} {t:8s} rows: {tp.row_filter or 'all'}; "
              f"denied columns: {', '.join(tp.deny_columns) or 'none'}")

    p("\n== acme:analyst: lake table only ==")
    r = acme.query("SELECT * FROM orders LIMIT 3")
    p(f"  governed: {r['governed_sql']}")
    p(f"  columns:  {r['columns']}")

    p("\n== acme:analyst: call CRM tool, then join with the lake ==")
    h = acme.call_tool("crm_accounts")
    r = acme.query(JOIN_SQL.format(h=h))
    p(f"  handle {h}; governed: {r['governed_sql']}")
    for row in r["rows"]:
        p(f"    {row}")

    p("\n== globex:analyst: same question, same code ==")
    globex = session(snapshot, "globex", "analyst", con, crm)
    hg = globex.call_tool("crm_accounts", segment="enterprise")
    for row in globex.query(JOIN_SQL.format(h=hg))["rows"]:
        p(f"    {row}")

    p("\n== Refusals (all before the engine) ==")
    attempts = [
        ("acme:analyst names a denied column", acme, "SELECT card_number FROM orders"),
        ("acme:analyst reads globex's handle", acme, f"SELECT * FROM {hg}"),
        ("acme:viewer has DESCRIBE only", session(snapshot, "acme", "viewer", con, crm),
         "SELECT count(*) FROM orders"),
        ("unmapped principal", session(snapshot, "initech", "analyst", con, crm),
         "SELECT count(*) FROM orders"),
    ]
    for label, s, sql in attempts:
        try:
            s.query(sql)
            p(f"  {label}: NOT refused (unexpected)")
        except Exception as e:
            p(f"  {label}: refused -> {e}")
    for label, call in [
        ("acme:viewer calls the CRM tool", lambda: session(snapshot, "acme", "viewer", con, crm).call_tool("crm_accounts")),
        ("model tries to pass tenant='globex'", lambda: acme.call_tool("crm_accounts", tenant="globex")),
    ]:
        try:
            call()
            p(f"  {label}: NOT refused (unexpected)")
        except fed.FederationError as e:
            p(f"  {label}: refused -> {e}")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=str(FIXTURE),
                    help="Lake Formation snapshot JSON (default: offline fixture)")
    ap.add_argument("--s3tables-arn", help="use a real S3 Tables bucket as the lake")
    ap.add_argument("--region", default="us-east-1")
    a = ap.parse_args()
    snapshot = json.loads(pathlib.Path(a.snapshot).read_text())
    con = duckdb.connect()
    crm = build_crm()
    with tempfile.TemporaryDirectory() as tmp:
        if a.s3tables_arn:
            attach_s3tables(con, a.s3tables_arn, a.region)
        else:
            build_lake(con, pathlib.Path(tmp))
        print("\n".join(run(snapshot, con, crm)))
        con.close()


if __name__ == "__main__":
    main()
