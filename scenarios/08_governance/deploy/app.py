#!/usr/bin/env python3
"""
Governed AgentCore Runtime entrypoint (scenario 08 in the cloud).

Each session embeds DuckDB, reads shared S3 Parquet via httpfs, and runs every
statement through the govern -> cost -> execute -> shape pipeline under the
CALLER'S identity. Identity comes from the verified JWT claims the AgentCore
inbound authorizer puts on the request context (custom:tenant / custom:role) —
NOT from the payload. Fail-closed: no claims => deny-all.

Local test:  python app.py --as acme:analyst '{"prompt":"how many trips"}'
"""
from __future__ import annotations
import json
import os
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from data_agent import governance as gov       # noqa: E402
from data_agent import context as ctx           # noqa: E402
from data_agent import pipeline as pl           # noqa: E402

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_ROOT = os.environ.get("DATA_ROOT", "s3://cdh-ingest-demo/duckdb-demo/nyc_taxi")
TRIPS = f"read_parquet('{S3_ROOT}/**/*.parquet')"

# Policies keyed by tenant:role. RLS/CLS on the taxi table; the raw source is the
# read_parquet glob, aliased to the logical name `trips` via a view at connect.
POLICIES = {
    "acme:admin":   gov.Policy(unrestricted=True),
    "acme:analyst": gov.Policy(tables={"trips": gov.TablePolicy(
        row_filter="payment_type = 1", deny_columns=("tip_amount",))}),
    "acme:junior":  gov.Policy(tables={"trips": gov.TablePolicy(
        row_filter="payment_type = 1", deny_columns=("tip_amount", "fare_amount"))}),
}
PARTITIONED: dict[str, str] = {}                 # single-month demo; no partition gate

_con = None
_store_by_owner: dict[str, object] = {}


def _conn():
    global _con
    if _con is None:
        import duckdb
        _con = duckdb.connect()
        _con.execute("INSTALL httpfs; LOAD httpfs;")
        _con.execute(f"CREATE OR REPLACE SECRET s3 "
                     f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
        _con.execute(f"CREATE OR REPLACE VIEW trips AS SELECT * FROM {TRIPS}")
    return _con


def _store(owner: str):
    if owner not in _store_by_owner:
        _store_by_owner[owner] = ctx.ResultStore(_conn(), owner=owner)
    return _store_by_owner[owner]


def _rule_plan(q: str) -> str | None:
    """NL -> SQL over the logical `trips` table (governance rewrites it)."""
    s = q.lower()
    def has(*w): return any(re.search(rf"\b{re.escape(x)}\b", s) for x in w)
    if has("how") and "many" in s and has("trip", "trips"):
        return "SELECT count(*) AS trips FROM trips"
    if has("busiest", "top"):
        n = (re.search(r"\b(\d{1,3})\b", s) or [None, "10"])[1] if re.search(r"\d", s) else "10"
        return f"SELECT PULocationID AS zone, count(*) AS trips FROM trips GROUP BY zone ORDER BY trips DESC LIMIT {n}"
    if "tip" in s and "hour" in s:
        return "SELECT hour(tpep_pickup_datetime) AS hr, round(avg(tip_amount),2) AS avg_tip FROM trips GROUP BY hr ORDER BY hr"
    if "payment" in s:
        return "SELECT payment_type, count(*) AS trips FROM trips GROUP BY payment_type ORDER BY trips DESC"
    return None


def handle(payload: dict, tenant: str | None, role: str | None) -> dict:
    q = (payload or {}).get("prompt", "").strip()
    if not q:
        return {"error": "empty prompt"}
    sql = _rule_plan(q)
    if sql is None:
        return {"error": f"unrecognized question: {q!r}",
                "hint": "how many trips / busiest N zones / tip by hour / payment"}
    owner = f"{tenant}:{role}" if tenant and role else "anonymous"
    out = pl.run_statement(sql, tenant, role, policies=POLICIES,
                           partitioned=PARTITIONED, store=_store(owner))
    a = out["audit"]
    trace = {"principal": a.principal, "stage": a.stage_reached,
             "rls_applied": a.rls_applied, "cls_excluded": a.cls_excluded}
    if "refused" in out:
        return {"refused": out["refused"], "trace": trace}
    r = out["result"]
    return {"sql": out["governed_sql"], "trace": trace,
            "row_count": r.get("row_count"), "handle": r.get("handle"),
            "rows": r.get("rows"), "samples": r.get("samples")}


def _claims_from_context(context) -> tuple[str | None, str | None]:
    """Pull custom:tenant / custom:role from the AgentCore request context JWT."""
    try:
        claims = (getattr(context, "request", {}) or {}).get("claims", {})
        return claims.get("custom:tenant"), claims.get("custom:role")
    except Exception:
        return None, None


try:
    from bedrock_agentcore import BedrockAgentCoreApp
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context=None):
        tenant, role = _claims_from_context(context)
        return handle(payload, tenant, role)

    if __name__ == "__main__" and os.environ.get("DOCKER_CONTAINER"):
        app.run()
except ImportError:
    pass


if __name__ == "__main__" and not os.environ.get("DOCKER_CONTAINER"):
    # local: python app.py --as acme:analyst '{"prompt":"how many trips"}'
    tenant = role = None
    argv = sys.argv[1:]
    if argv and argv[0] == "--as":
        tenant, _, role = argv[1].partition(":")
        argv = argv[2:]
    payload = json.loads(argv[0]) if argv else {"prompt": "how many trips"}
    print(json.dumps(handle(payload, tenant, role), default=str, indent=2))
