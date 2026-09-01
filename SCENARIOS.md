# Scenarios

Status legend: ✅ implemented · 🧪 proposed / next · 💡 idea

| # | Scenario | DuckDB strength shown | Status |
|---|----------|-----------------------|--------|
| 01 | **NYC Taxi analytics** | Query 3M-row Parquet directly, no load; window fns, quantiles, CSV-dim join; DuckDB vs Pandas benchmark; HTML report | ✅ implemented |
| 02 | **httpfs / S3 remote Parquet** | Query Parquet on S3/HTTP without downloading; partition pruning; hive-partitioned globs | ✅ implemented |
| 03 | **CSV → Parquet ETL** | DuckDB as a lightweight ETL engine: type/clean messy CSV, `COPY ... TO` partitioned Parquet, then query | ✅ implemented |
| 04 | **Chat BI (NL → SQL)** | NL questions → DuckDB SQL over Parquet; rule-based planner + Bedrock LLM hook; DuckDB as ad-hoc OLAP accelerator | ✅ implemented |
| 05 | **SQL over Pandas DataFrames** | Zero-copy SQL over in-memory DataFrames; mix Python + SQL in a notebook flow | 💡 idea |
| 06 | **Log / observability analytics** | Read NDJSON/CSV logs, p50/p95/p99 latency, error rates, time-bucket rollups | 💡 idea |
| 07 | **Multi-agent OLAP on AgentCore** | Where to install DuckDB for cost/perf when many agents query it (embedded per-agent vs shared query service) | 💡 idea (design) |

---

## 01 — NYC Taxi analytics ✅

`scenarios/01_nyc_taxi/`

- `get_data.sh` — fetch Jan-2024 yellow-taxi Parquet (~48MB, 2.96M rows) + zone lookup CSV.
- `analytics.py` — 6 analytical queries: dataset overview, revenue/tips by hour,
  trip-distance percentiles (exact + `approx_quantile`), busiest pickup zones
  (Parquet ⨝ CSV), payment-type mix (window fn), daily 7-day moving average,
  airport-trip economics.
- `benchmark.py` — same group-by-hour aggregate in DuckDB vs Pandas.
  Result: **DuckDB ~2.5× faster** (77ms vs 195ms best-of-5) and never
  materializes all 19 columns.
- `report.py` — emits a single self-contained `report.html` with inline-SVG
  charts (no plotting dependency).

Key findings (Jan 2024): 2.96M → 2.72M clean rows; tip % peaks ~20.7% at 6pm;
JFK is the #1 revenue pickup zone ($11.1M); 83.5% pay by card and 95% of those
tip, while cash trips record $0 tips (data-quality gotcha).

## 02 — httpfs / S3 remote Parquet ✅

`scenarios/02_httpfs_s3/`

- `remote_parquet.py` — `INSTALL httpfs; LOAD httpfs;` + a `credential_chain`
  S3 secret, then `read_parquet('s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/…')`:
  row count, a 3-column aggregate pushed down over S3, and hive-partition
  pruning on `year=/month=`. Auto-detects: queries live if the objects exist,
  else prints the seed command and exits.
- `seed_s3.sh` — one-time uploader (run in a terminal with S3-write creds; the
  Kiro Crew agent is blocked from S3 writes) that lays the local taxi Parquet out
  hive-partitioned into the bucket.

Motivation: query a data lake in place — no download, no cluster, pay only for
the bytes scanned. This is the pattern an embedded per-agent DuckDB uses.

## 03 — CSV → Parquet ETL ✅

`scenarios/03_csv_to_parquet_etl/`

- `etl.py` — fully self-contained. Synthesizes a deliberately messy CSV (mixed
  case, blank fields, quoted thousands-separators, a junk row, bad quantities),
  then `read_csv(ignore_errors=true)` → clean/cast (`try_cast`, `trim`, `lower`,
  strip `,`) → `COPY … TO (FORMAT parquet, PARTITION_BY (dt), COMPRESSION zstd)`
  → queries the output back.
- Verified: 50,001 raw → 41,599 clean rows (8,402 dropped), 7 daily partitions,
  **CSV 2.70 MB → Parquet 0.34 MB (7.9× smaller)**. Run this inside a Lambda
  (small/streaming) or a Fargate task (big batch).

## 04 — Chat BI (NL → SQL) ✅

`scenarios/04_chat_bi/`

- `chat_bi.py` — plain-English question → DuckDB SQL over the taxi Parquet →
  answer + a tiny inline bar chart, no hand-written SQL. The NL→SQL layer is
  **pluggable**: a deterministic offline **rule-based planner** by default (no API
  key, CI-friendly), and an **LLM planner hook** (`llm_plan`, Bedrock Converse)
  with a read-only-SELECT guardrail for open-ended questions. `--repl` for
  interactive use, or pass a question as an argument.
- Verified offline: "how many trips" → 2,869,697; "busiest 5 zones", "avg tip by
  hour", "payment mix", "revenue by day" all produce correct SQL + charts.

Architecture (from the thread): NL→DuckDB→Parquet-on-S3 is the cheapest start;
add Athena only when data outgrows single-node, and a semantic layer (Cube/dbt)
only when you need governed metrics — don't stack redundant engines.

## 07 — Multi-agent OLAP on AgentCore 💡

Design note: for many agents querying the same data, prefer **DuckDB embedded in
each agent runtime** (zero idle cost, scales with the agents) reading shared
**Parquet on S3** via httpfs, over standing up a shared DuckDB service. See the
thread discussion for the cost/perf tradeoff.
