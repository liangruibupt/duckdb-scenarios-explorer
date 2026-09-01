# Scenarios

Status legend: ✅ implemented · 🧪 proposed / next · 💡 idea

| # | Scenario | DuckDB strength shown | Status |
|---|----------|-----------------------|--------|
| 01 | **NYC Taxi analytics** | Query 3M-row Parquet directly, no load; window fns, quantiles, CSV-dim join; DuckDB vs Pandas benchmark; HTML report | ✅ implemented |
| 02 | **httpfs / S3 remote Parquet** | Query Parquet on S3/HTTP without downloading; partition pruning; hive-partitioned globs | ✅ implemented |
| 03 | **CSV → Parquet ETL** | DuckDB as a lightweight ETL engine: type/clean messy CSV, `COPY ... TO` partitioned Parquet, then query | ✅ implemented |
| 04 | **Chat BI (NL → SQL)** | NL questions → DuckDB SQL over Parquet; rule-based planner + Bedrock LLM hook; DuckDB as ad-hoc OLAP accelerator | ✅ implemented |
| 05 | **SQL over Pandas DataFrames** | Zero-copy SQL over in-memory DataFrames; mix Python + SQL in a notebook flow | ✅ implemented |
| 06 | **Log / observability analytics** | Read NDJSON/CSV logs, p50/p95/p99 latency, error rates, time-bucket rollups | ✅ implemented |
| 07 | **Multi-agent OLAP on AgentCore** | Embedded-per-agent DuckDB + shared hive-partitioned Parquet; concurrent multi-reader fan-out, partition pruning | ✅ implemented + [DESIGN.md](scenarios/07_multiagent_agentcore/DESIGN.md) |

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

## 05 — SQL over Pandas DataFrames ✅

`scenarios/05_sql_over_dataframes/`

- `sql_over_df.py` — DuckDB queries an in-memory Pandas DataFrame **by variable
  name** with no copy and no load step: aggregate over a DataFrame, DataFrame ⨝
  DataFrame, a window function (share-of-customer + rank), a DataFrame ⨝
  Parquet-on-disk join in one query, and the result handed back as both Pandas
  (`.df()`) and Arrow (`.arrow()`). Self-contained (builds its own frames; the
  Parquet join uses scenario 01's taxi file if present).
- The point: stay in Python, reach for SQL exactly where Pandas gets awkward.

## 06 — Log / observability analytics ✅

`scenarios/06_log_analytics/`

- `log_analytics.py` — self-contained. Synthesizes a realistic NDJSON access log
  (200k lines, per-endpoint latency/error profiles, an injected 14:10–14:13
  latency spike), then `read_json_auto` + SQL: **p50/p95/p99 latency per
  endpoint** (`approx_quantile`), **4xx/5xx error rate per endpoint**,
  **per-minute `time_bucket` rollup** (the spike surfaces at ~550ms p95 vs ~140ms
  baseline), and an overall SLO summary.
- The point: native NDJSON analytics with no parse/ETL step and no log service —
  the pattern for ad-hoc "why was it slow at 14:03?" over a log dump on disk/S3.

## 07 — Multi-agent OLAP on AgentCore ✅ (implemented + design)

`scenarios/07_multiagent_agentcore/` — design doc `DESIGN.md` (inspect → plan →
implement → test) plus a runnable demo `agent_query.py`: each `Agent` embeds its
own DuckDB connection over a shared hive-partitioned Parquet lake; `fan_out()`
runs N agents concurrently and shows they return identical results with no
contention (multi-reader), plus a partition-pruned per-day read. Local lake by
default (offline/CI), or point at S3 with `DATA_ROOT=s3://bucket/prefix`.
Recommendation: **DuckDB embedded per-agent** + hive-partitioned **Parquet on
S3** via `httpfs`, over a shared DuckDB service. Writes route to OLTP (Aurora) or
a single-writer append-Parquet path. Add Athena only past single-node scale; add
a semantic layer only for governed metrics.
