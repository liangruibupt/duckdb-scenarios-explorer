#!/usr/bin/env python3
"""
Scenario 06 -- Log / observability analytics with DuckDB.

Point DuckDB at newline-delimited JSON access logs (the shape most web servers
and load balancers emit) and get real SLO analytics with SQL:
  - latency percentiles p50 / p95 / p99 (approx_quantile over millions of rows)
  - error rate (4xx / 5xx) per endpoint
  - requests-per-minute time buckets (time_bucket rollup)
  - top slow endpoints

DuckDB reads NDJSON natively (`read_json_auto`), so there is no parse/ETL step
and no log-analytics service to run. This is the pattern for ad-hoc "why was the
service slow at 14:03?" investigations over a dump of logs on disk or S3.

Self-contained: synthesizes a realistic NDJSON access log first.

  python log_analytics.py     # -> writes access.ndjson, prints the analysis
"""
from __future__ import annotations
import json
import os
import random
import datetime as dt
import duckdb

LOG = "access.ndjson"
ENDPOINTS = ["/api/search", "/api/cart", "/api/checkout", "/api/product",
             "/api/login", "/health", "/api/recommend"]


def make_log(path: str, n: int = 200_000) -> None:
    """Synthesize NDJSON access logs with realistic latency + status mix,
    including a latency spike window and endpoint-specific error rates."""
    random.seed(11)
    start = dt.datetime(2024, 1, 15, 14, 0, 0)
    # per-endpoint base latency (ms) and error probability
    base = {
        "/api/search": (45, 0.01), "/api/cart": (25, 0.005),
        "/api/checkout": (120, 0.03), "/api/product": (30, 0.008),
        "/api/login": (60, 0.02), "/health": (3, 0.0),
        "/api/recommend": (80, 0.015),
    }
    with open(path, "w") as f:
        for i in range(n):
            ep = random.choices(ENDPOINTS,
                                weights=[30, 20, 8, 25, 10, 15, 12])[0]
            b, err_p = base[ep]
            ts = start + dt.timedelta(milliseconds=random.randint(0, 30*60*1000))
            # inject a latency spike between 14:10 and 14:13
            spike = 4.0 if dt.datetime(2024,1,15,14,10) <= ts <= dt.datetime(2024,1,15,14,13) else 1.0
            latency = max(1, int(random.lognormvariate(0, 0.5) * b * spike))
            if random.random() < err_p:
                status = random.choice([500, 502, 503, 400, 404])
            else:
                status = random.choice([200, 200, 200, 200, 304])
            f.write(json.dumps({
                "ts": ts.isoformat(timespec="milliseconds"),
                "method": "GET" if ep != "/api/checkout" else "POST",
                "path": ep,
                "status": status,
                "latency_ms": latency,
                "bytes": random.randint(200, 20000),
            }) + "\n")


def show(con, label, sql):
    print(f"\n# {label}")
    print(con.execute(sql).df().to_string(index=False))


def main() -> None:
    make_log(LOG)
    con = duckdb.connect()
    # read_json_auto infers the schema from the NDJSON; ts becomes a TIMESTAMP.
    con.execute(f"""
        CREATE OR REPLACE VIEW logs AS
        SELECT ts::TIMESTAMP AS ts, method, path, status::INT AS status,
               latency_ms::DOUBLE AS latency_ms, bytes::BIGINT AS bytes
        FROM read_json_auto('{LOG}')
    """)

    total = con.execute("SELECT count(*) FROM logs").fetchone()[0]
    print(f"Analyzing {total:,} log lines from {LOG}")

    show(con, "Latency percentiles per endpoint (ms)", """
        SELECT path,
               count(*)                                    AS reqs,
               round(approx_quantile(latency_ms, 0.50), 1) AS p50,
               round(approx_quantile(latency_ms, 0.95), 1) AS p95,
               round(approx_quantile(latency_ms, 0.99), 1) AS p99,
               max(latency_ms)                             AS max_ms
        FROM logs GROUP BY path ORDER BY p99 DESC
    """)

    show(con, "Error rate per endpoint (4xx / 5xx)", """
        SELECT path,
               count(*)                                              AS reqs,
               round(100.0 * count_if(status >= 500) / count(*), 2)  AS pct_5xx,
               round(100.0 * count_if(status >= 400 AND status < 500) / count(*), 2) AS pct_4xx
        FROM logs GROUP BY path
        HAVING pct_5xx > 0 OR pct_4xx > 0
        ORDER BY pct_5xx DESC
    """)

    show(con, "Requests + p95 latency per minute (spike shows up 14:10-14:13)", """
        SELECT time_bucket(INTERVAL '1 minute', ts)          AS minute,
               count(*)                                       AS reqs,
               round(approx_quantile(latency_ms, 0.95), 1)    AS p95_ms
        FROM logs GROUP BY minute ORDER BY p95_ms DESC LIMIT 6
    """)

    show(con, "Overall SLO summary", """
        SELECT count(*)                                            AS total_reqs,
               round(100.0 * count_if(status < 400) / count(*), 2) AS pct_success,
               round(approx_quantile(latency_ms, 0.50), 1)         AS p50,
               round(approx_quantile(latency_ms, 0.99), 1)         AS p99
        FROM logs
    """)

    print("\nDone -- native NDJSON analytics, no parsing step, no log service.")


def load_to_ducklake_with_timetravel(log_path: str, catalog_dir: str) -> dict:
    """Append log rows into a MANAGED table in two snapshots (pre-spike window,
    then the spike window), so you can ask 'what did the table look like BEFORE
    the 14:10 spike?' via time-travel -- impossible on an immutable NDJSON dump.
    Returns a summary dict for verification."""
    import duckdb as _d
    con = _d.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    cat = os.path.join(catalog_dir, "logs.ducklake")
    data = os.path.join(catalog_dir, "data")
    con.execute(f"ATTACH 'ducklake:{cat}' AS lake (DATA_PATH '{data}')")
    con.execute("USE lake")
    con.execute("""CREATE TABLE logs (ts TIMESTAMP, path VARCHAR, status INT,
                   latency_ms DOUBLE)""")
    src = (f"SELECT ts::TIMESTAMP, path, status::INT, latency_ms::DOUBLE "
           f"FROM read_json_auto('{log_path}')")

    # snapshot 1: only rows BEFORE the injected spike (< 14:10)
    con.execute(f"INSERT INTO logs {src} WHERE ts::TIMESTAMP < TIMESTAMP '2024-01-15 14:10:00'")
    v_pre = con.execute("SELECT max(snapshot_id) FROM ducklake_snapshots('lake')").fetchone()[0]
    # snapshot 2: the spike window and after (>= 14:10)
    con.execute(f"INSERT INTO logs {src} WHERE ts::TIMESTAMP >= TIMESTAMP '2024-01-15 14:10:00'")

    # p95 now (with spike) vs AS OF the pre-spike snapshot
    def p95(sql_tbl):
        return con.execute(
            f"SELECT round(approx_quantile(latency_ms,0.95),1) FROM {sql_tbl} "
            f"WHERE ts >= TIMESTAMP '2024-01-15 14:10:00' "
            f"AND ts < TIMESTAMP '2024-01-15 14:13:00'").fetchone()[0]
    now_spike = p95("logs")
    pre_rows = con.execute(
        f"SELECT count(*) FROM logs AT (VERSION => {v_pre}) "
        f"WHERE ts >= TIMESTAMP '2024-01-15 14:10:00'").fetchone()[0]
    return {"pre_spike_snapshot": v_pre,
            "spike_minutes_in_pre_snapshot": pre_rows,   # expect 0
            "current_spike_p95": now_spike}


if __name__ == "__main__":
    import sys, tempfile
    if len(sys.argv) > 1 and sys.argv[1] == "--ducklake":
        make_log(LOG, n=60_000)
        with tempfile.TemporaryDirectory() as tmp:
            r = load_to_ducklake_with_timetravel(LOG, tmp)
        print("DuckLake time-travel over logs:")
        print(f"  pre-spike snapshot: {r['pre_spike_snapshot']}")
        print(f"  spike-window rows visible in the pre-spike snapshot: "
              f"{r['spike_minutes_in_pre_snapshot']} (0 = time-travel works)")
        print(f"  current p95 during the spike window: {r['current_spike_p95']} ms")
    else:
        main()
