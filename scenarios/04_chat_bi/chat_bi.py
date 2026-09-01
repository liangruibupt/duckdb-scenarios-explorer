#!/usr/bin/env python3
"""
Scenario 04 -- Chat BI: ask questions in natural language, DuckDB answers.

Turns a plain-English question into DuckDB SQL over the NYC taxi Parquet, runs
it, and prints the answer + a tiny inline bar chart -- no hand-written SQL.

The NL->SQL layer is PLUGGABLE:
  - default: a deterministic, offline rule-based planner (no API key needed) that
    covers the common question shapes over this schema. Great for a demo/CI.
  - production: swap in an LLM planner (Bedrock) -- see llm_plan() for the exact
    prompt + guardrail. The rest of the pipeline (execute + render) is identical.

Usage:
  python chat_bi.py                       # runs a scripted set of demo questions
  python chat_bi.py "your question ..."   # ask one question
  python chat_bi.py --repl                # interactive prompt

Needs ../01_nyc_taxi/data/yellow_2024-01.parquet (run its get_data.sh first).
"""
from __future__ import annotations
import os
import re
import sys
import duckdb

DATA = "../01_nyc_taxi/data/yellow_2024-01.parquet"
ZONES = "../01_nyc_taxi/data/taxi_zone_lookup.csv"

SCHEMA_DOC = """
Table trips (NYC yellow taxi, Jan 2024), columns:
  tpep_pickup_datetime TIMESTAMP, trip_distance DOUBLE, passenger_count BIGINT,
  fare_amount DOUBLE, tip_amount DOUBLE, total_amount DOUBLE,
  payment_type BIGINT (1=card,2=cash), PULocationID INT, DOLocationID INT
Dimension zones(LocationID INT, Borough, Zone) joined on PULocationID=LocationID.
"""


# --- rule-based NL->SQL planner (offline default) ---------------------------

def rule_plan(q: str) -> str | None:
    """Map common question shapes to SQL. Returns None if unrecognized."""
    s = q.lower().strip()

    def has(*words) -> bool:
        # whole-word match so 'mean' does not fire on 'meaning', etc.
        return any(re.search(rf"\b{re.escape(w)}\b", s) for w in words)

    base = f"read_parquet('{DATA}')"
    clean = (f"(SELECT * FROM {base} WHERE trip_distance>0 AND fare_amount>0 "
             f"AND tpep_pickup_datetime >= TIMESTAMP '2024-01-01' "
             f"AND tpep_pickup_datetime < TIMESTAMP '2024-02-01')")

    if has("how") and "many" in s and has("trip", "trips", "ride", "rides"):
        return f"SELECT count(*) AS trips FROM {clean}"

    if has("busiest", "top") and has("zone", "zones", "pickup", "borough"):
        col = "z.Borough" if has("borough") else "z.Zone"
        n = _num(s, default=10)
        return (f"SELECT {col} AS name, count(*) AS trips "
                f"FROM {clean} c JOIN read_csv('{ZONES}') z "
                f"ON c.PULocationID=z.LocationID GROUP BY name "
                f"ORDER BY trips DESC LIMIT {n}")

    if "by hour" in s or "per hour" in s or "hour of day" in s:
        metric, expr = _metric(s)
        return (f"SELECT hour(tpep_pickup_datetime) AS hr, {expr} AS {metric} "
                f"FROM {clean} GROUP BY hr ORDER BY hr")

    if has("average", "avg", "mean"):
        metric, expr = _metric(s)
        return f"SELECT {expr} AS {metric} FROM {clean}"

    if has("payment"):
        return (f"SELECT CASE payment_type WHEN 1 THEN 'card' WHEN 2 THEN 'cash' "
                f"ELSE 'other' END AS payment, count(*) AS trips "
                f"FROM {clean} GROUP BY payment ORDER BY trips DESC")

    if has("revenue", "total"):
        if has("day", "daily"):
            return (f"SELECT tpep_pickup_datetime::DATE AS day, "
                    f"round(sum(total_amount),0) AS revenue "
                    f"FROM {clean} GROUP BY day ORDER BY day")
        return f"SELECT round(sum(total_amount),0) AS revenue FROM {clean}"

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


# --- LLM planner hook (production path; not called by default) ---------------

def llm_plan(q: str) -> str:  # pragma: no cover - reference implementation
    """Swap this in for open-ended questions. Uses Bedrock Converse.
    Guardrail: the model returns ONLY a single read-only SELECT; we reject
    anything that isn't (no INSERT/UPDATE/DELETE/COPY/ATTACH)."""
    import boto3
    prompt = (f"You translate questions to DuckDB SQL.\n{SCHEMA_DOC}\n"
              f"Use read_parquet('{DATA}') as the trips source and "
              f"read_csv('{ZONES}') as zones. Return ONLY one SELECT statement, "
              f"no prose, no code fences.\nQuestion: {q}")
    br = boto3.client("bedrock-runtime", region_name="us-east-1")
    r = br.converse(
        modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0})
    sql = r["output"]["message"]["content"][0]["text"].strip().strip("`")
    if not re.match(r"(?is)^\s*select\b", sql) or re.search(
            r"(?i)\b(insert|update|delete|copy|attach|drop|create)\b", sql):
        raise ValueError(f"Refusing non-SELECT SQL from model: {sql[:120]}")
    return sql


def plan(q: str, use_llm: bool) -> str:
    if use_llm:
        return llm_plan(q)
    sql = rule_plan(q)
    if sql is None:
        raise SystemExit(
            f"Rule planner didn't recognize: {q!r}\n"
            f"Try phrasings like 'how many trips', 'busiest 5 zones', "
            f"'average tip by hour', 'payment mix', 'revenue by day', or set "
            f"USE_LLM=1 to use the Bedrock planner.")
    return sql


# --- execute + render --------------------------------------------------------

def bar(label: str, value: float, maxv: float, width: int = 30) -> str:
    fill = int(value / maxv * width) if maxv else 0
    return f"  {label:<22} {'#'*fill}{'.'*(width-fill)} {value:,.2f}"


def answer(con, q: str, use_llm: bool) -> None:
    sql = plan(q, use_llm)
    df = con.execute(sql).fetchdf()
    print(f"\nQ: {q}")
    print(f"   SQL> {sql}")
    if df.shape == (1, 1):
        print(f"   = {df.iat[0,0]:,}")
        return
    print(df.to_string(index=False))
    # tiny bar chart if the result is (label, number)
    if df.shape[1] == 2 and len(df) <= 30:
        lab, val = df.columns
        try:
            maxv = float(df[val].max())
            print()
            for _, row in df.iterrows():
                print(bar(str(row[lab]), float(row[val]), maxv))
        except (TypeError, ValueError):
            pass


DEMO = [
    "How many trips were there?",
    "What are the busiest 5 pickup zones?",
    "Average tip by hour of day",
    "Payment mix",
    "Revenue by day",
]


def main() -> None:
    if not os.path.exists(DATA):
        raise SystemExit(f"Missing {DATA} -- run ../01_nyc_taxi/get_data.sh first")
    use_llm = os.environ.get("USE_LLM") == "1"
    con = duckdb.connect()

    args = sys.argv[1:]
    if args and args[0] == "--repl":
        print("Chat BI over NYC taxi data. Ctrl-D to quit.")
        while True:
            try:
                q = input("\nask> ").strip()
            except EOFError:
                break
            if q:
                try:
                    answer(con, q, use_llm)
                except SystemExit as e:
                    print(e)
    elif args:
        answer(con, " ".join(args), use_llm)
    else:
        for q in DEMO:
            answer(con, q, use_llm)


if __name__ == "__main__":
    main()
