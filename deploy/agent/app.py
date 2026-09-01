#!/usr/bin/env python3
"""
AgentCore Runtime entrypoint -- chat-BI agent (scenarios 04 + 07).

Embeds DuckDB in-process (scenario 07 pattern) and reads shared hive-partitioned
Parquet on S3 via httpfs (scenario 02). Turns a natural-language `prompt` into
DuckDB SQL (scenario 04's rule-based planner, with an optional Bedrock LLM
planner), runs it, and returns {sql, rows, engine}.

Runs as a BedrockAgentCoreApp when containerized (agentcore launch). Locally you
can import `handle` and call it directly for testing.
"""
from __future__ import annotations
import os
import re
import duckdb

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_ROOT = os.environ.get(
    "DATA_ROOT", "s3://cdh-ingest-demo/duckdb-demo/nyc_taxi")
TRIPS = f"read_parquet('{S3_ROOT}/**/*.parquet')"

# one embedded connection per container process (warm reuse across invocations)
_con: duckdb.DuckDBPyConnection | None = None


def _conn() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        c = duckdb.connect()
        c.execute("INSTALL httpfs; LOAD httpfs;")
        c.execute(f"CREATE OR REPLACE SECRET s3 "
                  f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
        _con = c
    return _con


CLEAN = (f"(SELECT * FROM {TRIPS} WHERE trip_distance>0 AND fare_amount>0)")


def rule_plan(q: str) -> str | None:
    """NL -> DuckDB SQL for common taxi questions (word-boundary matched)."""
    s = q.lower().strip()

    def has(*ws):
        return any(re.search(rf"\b{re.escape(w)}\b", s) for w in ws)

    if has("how") and "many" in s and has("trip", "trips", "ride", "rides"):
        return f"SELECT count(*) AS trips FROM {CLEAN}"
    if has("busiest", "top") and has("zone", "zones", "pickup"):
        n = _num(s, 10)
        return (f"SELECT PULocationID AS zone_id, count(*) AS trips "
                f"FROM {CLEAN} GROUP BY zone_id ORDER BY trips DESC LIMIT {n}")
    if "by hour" in s or "per hour" in s or "hour of day" in s:
        metric, expr = _metric(s)
        return (f"SELECT hour(tpep_pickup_datetime) AS hr, {expr} AS {metric} "
                f"FROM {CLEAN} GROUP BY hr ORDER BY hr")
    if has("average", "avg", "mean"):
        metric, expr = _metric(s)
        return f"SELECT {expr} AS {metric} FROM {CLEAN}"
    if has("payment"):
        return ("SELECT CASE payment_type WHEN 1 THEN 'card' WHEN 2 THEN 'cash' "
                f"ELSE 'other' END AS payment, count(*) AS trips "
                f"FROM {CLEAN} GROUP BY payment ORDER BY trips DESC")
    if has("revenue", "total"):
        return f"SELECT round(sum(total_amount),0) AS revenue FROM {CLEAN}"
    return None


def _metric(s: str):
    if "tip" in s:      return "avg_tip", "round(avg(tip_amount),2)"
    if "distance" in s: return "avg_distance", "round(avg(trip_distance),2)"
    if "revenue" in s or "total" in s: return "revenue", "round(sum(total_amount),0)"
    if "trip" in s or "ride" in s or "count" in s: return "trips", "count(*)"
    return "avg_fare", "round(avg(fare_amount),2)"


def _num(s: str, default: int) -> int:
    m = re.search(r"\b(\d{1,3})\b", s)
    return int(m.group(1)) if m else default


def llm_plan(q: str) -> str:
    """Bedrock Converse planner (used when USE_LLM=1). Read-only SELECT only."""
    import boto3
    prompt = (f"Translate to ONE DuckDB SELECT over {TRIPS} (yellow taxi: "
              f"tpep_pickup_datetime, trip_distance, fare_amount, tip_amount, "
              f"total_amount, payment_type, PULocationID). Return only SQL.\n"
              f"Q: {q}")
    br = boto3.client("bedrock-runtime", region_name=REGION)
    r = br.converse(modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"maxTokens": 400, "temperature": 0})
    sql = r["output"]["message"]["content"][0]["text"].strip().strip("`")
    if not re.match(r"(?is)^\s*select\b", sql) or re.search(
            r"(?i)\b(insert|update|delete|copy|attach|drop|create)\b", sql):
        raise ValueError("model returned non-SELECT SQL")
    return sql


def handle(payload: dict) -> dict:
    """Core logic -- importable for local tests, wrapped by the entrypoint."""
    q = (payload or {}).get("prompt", "").strip()
    if not q:
        return {"error": "empty prompt", "hint": "send {\"prompt\": \"...\"}"}
    use_llm = os.environ.get("USE_LLM") == "1"
    try:
        sql = llm_plan(q) if use_llm else rule_plan(q)
        engine = "llm" if use_llm else "rule"
        if sql is None:
            return {"error": f"unrecognized question: {q!r}",
                    "hint": "try: how many trips, busiest 5 zones, "
                            "average tip by hour, payment mix, revenue"}
        rows = _conn().execute(sql).fetchdf().to_dict(orient="records")
        return {"sql": sql, "engine": engine, "rows": rows}
    except Exception as e:                       # surface errors as data
        return {"error": str(e)[:300], "prompt": q}


# --- AgentCore wiring (only when the SDK is present / containerized) ---------
try:
    from bedrock_agentcore import BedrockAgentCoreApp
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload):
        return handle(payload)

    if __name__ == "__main__" and os.environ.get("DOCKER_CONTAINER"):
        app.run()
except ImportError:
    pass


if __name__ == "__main__" and not os.environ.get("DOCKER_CONTAINER"):
    # local smoke: python app.py "busiest 5 zones"
    import json, sys
    q = " ".join(sys.argv[1:]) or "How many trips were there?"
    print(json.dumps(handle({"prompt": q}), default=str, indent=2))
