# Scenarios

Status legend: ✅ implemented · 🧪 proposed / next · 💡 idea

| # | Scenario | DuckDB strength shown | Status |
|---|----------|-----------------------|--------|
| 01 | **NYC Taxi analytics** | Query 3M-row Parquet directly, no load; window fns, quantiles, CSV-dim join; DuckDB vs Pandas benchmark; HTML report | ✅ implemented |
| 02 | **httpfs / S3 remote Parquet** | Query Parquet on S3/HTTP without downloading; partition pruning; hive-partitioned globs | 🧪 next |
| 03 | **CSV → Parquet ETL** | DuckDB as a lightweight ETL engine: type/clean messy CSV, `COPY ... TO` partitioned Parquet, then query | 🧪 next |
| 04 | **Chat BI (NL → SQL)** | LLM turns natural-language questions into DuckDB SQL over a lakehouse; DuckDB as ad-hoc OLAP accelerator | 🧪 next |
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

## 02 — httpfs / S3 remote Parquet 🧪

Show `INSTALL httpfs; LOAD httpfs;` + `read_parquet('s3://…/*.parquet')` with
credentials, and hive-partition pruning (`year=/month=`) so only relevant files
are scanned. Motivation: query a data lake in place, no download, no cluster.

## 03 — CSV → Parquet ETL 🧪

Ingest messy CSVs (`read_csv` auto-typing + `union_by_name`), clean/cast, then
`COPY (…) TO 'out' (FORMAT parquet, PARTITION_BY (…))`. Shows DuckDB as a single
-binary ETL step you can run in a Lambda/Fargate task or locally.

## 04 — Chat BI (NL → SQL) 🧪

Natural-language questions → DuckDB SQL, executed against Parquet/lakehouse,
answered in prose + a chart. DuckDB acts as the fast ad-hoc OLAP layer over
S3/Athena/Redshift-managed data. (Architecture discussion in the thread.)

## 07 — Multi-agent OLAP on AgentCore 💡

Design note: for many agents querying the same data, prefer **DuckDB embedded in
each agent runtime** (zero idle cost, scales with the agents) reading shared
**Parquet on S3** via httpfs, over standing up a shared DuckDB service. See the
thread discussion for the cost/perf tradeoff.
