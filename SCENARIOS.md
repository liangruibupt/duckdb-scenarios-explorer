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
| 07 | **Multi-agent OLAP on AgentCore** | Embedded-per-agent DuckDB + shared read layer (Parquet, and Iceberg on S3 Tables); concurrent multi-reader fan-out proven local AND against a live managed Iceberg table, partition pruning | ✅ implemented + [DESIGN.md](scenarios/07_multiagent_agentcore/DESIGN.md) |
| 08 | **Governed data agent (RLS/CLS + context + semantic)** | sqlglot RLS/CLS rewrite (fail-closed) + cost gate + result handles + history compression + govern→cost→execute pipeline + registered-metric semantic layer; wired into chat_bi | ✅ implemented + tested |
| 09 | **Iceberg / DuckLake table format** | ACID snapshots, time-travel (`AT VERSION`), schema evolution, row-level UPDATE/DELETE — what raw Parquet cannot do; local via DuckLake, cloud via `iceberg_scan` (S3 Tables) | ✅ implemented + tested |

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

## 08 — Governed data agent: RLS/CLS + context layer ✅

`scenarios/08_governance/data_agent/`

Brings the two layers from `aws-samples/sample-data-agent-on-duckdb` that turn a
naive NL→SQL tool into a *governed* agent. Spec: `specs/GOVERNANCE_SPEC.md`.

- `governance.py` — identity-aware **RLS/CLS rewrite before the engine** via
  sqlglot, fail-closed: deny-all floor for an unknown principal, RLS `row_filter`
  ANDed into every table reference, denied columns `EXCLUDE`d from `SELECT *` and
  a **clean rejection** when named explicitly, table allow-list, SELECT-only
  statement-shape allow-list (DML behind a `WITH` prefix refused), CTE cannot
  shadow a governed table, host-reaching paths refused for every role.
- `context.py` — **cost gate** (a raw partitioned source without a predicate on
  its partition column is refused; over-wide partition spans refused),
  **owner-bound result handles** (results over `MAX_RESULT_ROWS` become session
  temp tables `_r_<n>`; a foreign handle is refused before the engine), and
  **history compression** (old materialized-result blobs become one-line pointers
  once the model window passes `COMPRESSION_THRESHOLD`; current turn untouched).
- Tests: 42 offline, incl. a **persona × statement-shape governance matrix**
  whose expected outcome is derived from the policy (admin passes unchanged,
  analyst gets RLS+CLS on every shape, junior's denied column is refused on every
  shape).
- `pipeline.py` — **govern → cost → execute + shape** in one call
  (`run_statement`); the governed SQL (not the raw SQL) is what the cost gate and
  engine see, a refusal names its stage, and every statement emits an audit record.
- `semantic.py` — a **registered-metric layer**: `Registry` + `Metric`; a metric
  is called by name with allow-listed dimensions/time, compiles deterministically
  to one governed `SELECT`, and runs through the same pipeline (so RLS/CLS + cost
  gate still apply). An unregistered metric or an out-of-allow-list dimension is
  refused — no improvised SQL.
- Wired into `scenarios/04_chat_bi/chat_bi.py` via `--principal tenant:role` so a
  demo question runs the governed path; the default path is unchanged.

## 09 — Iceberg / DuckLake table format ✅

`scenarios/09_iceberg/tables.py` — proves the capabilities a raw Parquet glob
cannot give, offline via **DuckLake** (a local read/write Iceberg-style format:
SQL catalog + Parquet data): **ACID snapshots**, **time-travel**
(`… AT (VERSION => n)`), **schema evolution** (`ALTER TABLE … ADD COLUMN`, old
snapshots still read), and **row-level UPDATE/DELETE**. The cloud analogue is
Amazon S3 Tables (Iceberg REST), read via the `iceberg` extension's
`iceberg_scan`. Spec: `specs/ICEBERG_SPEC.md`.

**Iceberg pass across existing scenarios** (same spec):
- **02** — an Iceberg access path (`iceberg_scan`) beside the raw glob
  (`S3_TABLES_ICEBERG=…`), mirroring the aws-sample's path A/path B.
- **03** — a DuckLake managed-table ETL target (`etl.py --target ducklake`): two
  appends → two snapshots, each time-travellable.
- **06** — a DuckLake log mode (`log_analytics.py --ducklake`): append pre-spike
  then spike windows as snapshots, then "what did the table look like before the
  14:10 spike?" via time-travel.
- **07** — DESIGN.md updated: the shared read layer should be an Iceberg table on
  S3 once any agent writes (ACID + snapshot isolation), not a raw glob.
- **08** — the governance matrix gains an `iceberg` access-path column; the
  rewrite is identical on every path (name-based, format-agnostic) — 75/75 cells.

Engine note (DuckDB 1.5.5): `iceberg` is a reader (`iceberg_scan`,
`iceberg_snapshots`); `ducklake` is the read/write format used for the offline
differentiator demos.

### Learning point — DuckLake managed-table vs Amazon S3 Tables

Both are **Iceberg-style table formats** (a catalog + snapshots + ACID on top of
Parquet files). They differ in *where the catalog lives and who operates it* —
this repo uses DuckLake as the **offline stand-in** and S3 Tables as the **live
cloud** table, so the same concepts are provable in CI and demonstrated for real.

| | **DuckLake** | **Amazon S3 Tables** |
|---|---|---|
| Catalog | a local SQL DB file (`*.ducklake`) | AWS-managed **Iceberg REST** catalog |
| Data files | Parquet on local disk (or S3) | Parquet in the S3 Tables bucket |
| Runs where | in-process, **offline**, no AWS | AWS service (needs an account) |
| Table format | DuckLake's own (Iceberg-compatible direction) | **Apache Iceberg** (the standard) |
| Writes from DuckDB | `CREATE`/`INSERT`/`UPDATE`/`DELETE`/`ALTER` | `CREATE TABLE AS` + `INSERT` via the REST catalog (append-first); `iceberg_scan` on a bare metadata location is read-only |
| Maintenance | you compact | AWS auto-compacts |
| Multi-engine | DuckDB-centric today | any Iceberg reader (Athena, Spark, Trino, DuckDB) |
| Cost | free | S3 Tables storage + maintenance |
| Used in this repo for | offline differentiator demos + CI (09/03/06 tests) | the live table (`09/cloud_s3tables.py`, `02` path B) |

Rule of thumb: **DuckLake** to prove the *capabilities* cheaply and offline;
**S3 Tables** when you want a real, multi-engine, AWS-managed Iceberg table that
Athena/Spark/Trino can also read. Same query, same governance (scenario 08's
matrix proves the rewrite is identical across raw/s3t/glue/dl/iceberg paths);
only how the table name resolves to files differs.
