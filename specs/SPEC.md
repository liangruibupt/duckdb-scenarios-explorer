# Specs & Acceptance Criteria

This repo follows an **inspect → plan → implement → test** loop. This document is
the *inspect/spec* step: it states, per scenario, what "correct" means as
checkable invariants. `tests/` asserts these; CI keeps them green.

Test tiers:
- **offline** — self-contained, no network/data download (03, 05, 06, and the
  planner/logic parts of 04). Always run in CI.
- **data-gated** — needs the NYC taxi Parquet (`scenarios/01_nyc_taxi/data/`).
  Skipped automatically when the file is absent.
- **s3-gated** — needs live S3 objects under `s3://cdh-ingest-demo/duckdb-demo/`.
  Skipped unless `RUN_S3_TESTS=1` and credentials are present.

---

## 01 — NYC Taxi analytics  *(data-gated)*

Inputs: `yellow_2024-01.parquet` (~2.96M rows), `taxi_zone_lookup.csv`.

Invariants:
- The `clean` view drops rows and never adds them: `0 < clean_rows < raw_rows`.
- Hourly aggregate returns exactly 24 rows (hours 0–23), all trip counts > 0.
- Trip-distance percentiles are monotonic: `p50 ≤ p90 ≤ p99 ≤ max`.
- Busiest-zones join returns ≤ 10 rows, each with a non-null Borough/Zone and
  `trips > 0`.
- The 7-day moving average is never negative and never exceeds the running max
  daily count.

## 02 — httpfs / S3 remote Parquet  *(s3-gated)*

Inputs: hive-partitioned Parquet at
`s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/year=YYYY/month=MM/*.parquet`.

Invariants:
- The recursive glob `**/*.parquet` matches the two-level hive layout (the
  single-level `*/*.parquet` must NOT — this is the regression we fixed).
- `read_parquet(..., hive_partitioning=true)` exposes integer `year`/`month`
  columns; filtering `WHERE year=2024` prunes to only matching partitions.
- Row count off S3 equals the local file's row count for the same month.

## 03 — CSV → Parquet ETL  *(offline)*

Invariants:
- Cleaning is subtractive: `0 < clean_rows < raw_rows` (bad `qty ≤ 0`, junk row,
  and unparseable timestamps are dropped).
- Every surviving row has `qty > 0`, a non-null `ts`, and a non-null `amount`
  (the quoted thousands-comma must survive as data, not split the row — the
  regression we fixed).
- `COPY … PARTITION_BY (dt)` writes ≥ 1 Parquet part-file, and re-reading them
  round-trips the clean row count.
- Output Parquet is strictly smaller than the source CSV.

## 04 — Chat BI (NL → DuckDB SQL)  *(offline + data-gated)*

Invariants (planner logic — offline, no data needed):
- `rule_plan` returns a single `SELECT` for each supported question shape
  ("how many trips", "busiest N zones", "avg tip by hour", "payment mix",
  "revenue by day"); an unsupported question returns `None`.
- `_num` extracts the N from "busiest 5 zones" → 5, defaults otherwise.
- The `llm_plan` guardrail rejects any non-SELECT / DDL/DML SQL string.

Invariants (execution — data-gated):
- "How many trips" executes and returns a single positive integer.
- "busiest 5 zones" returns exactly 5 rows.

## 05 — SQL over Pandas DataFrames  *(offline)*

Invariants:
- A DataFrame is queryable by variable name (no registration): aggregate row
  count equals the DataFrame length.
- `df JOIN df` on `region_id` yields one row per region, and summed revenue
  equals the ungrouped total (join loses nothing).
- The window `pct_of_cust` per customer sums to ~100% within each partition.
- `.arrow()` result reads back into a table with the expected scalar values.

## 06 — Log / observability analytics  *(offline)*

Invariants:
- `read_json_auto` infers a usable schema; total lines match what was written.
- Latency percentiles per endpoint are monotonic (`p50 ≤ p95 ≤ p99 ≤ max`).
- Error-rate percentages are within [0, 100].
- The per-minute `time_bucket` rollup places the highest-p95 minute inside the
  injected spike window (14:10–14:13).
- Overall `pct_success` is within [0, 100] and p50 ≤ p99.

## 07 — Multi-agent OLAP on AgentCore  *(offline demo + design)*

Design doc: `scenarios/07_multiagent_agentcore/DESIGN.md`.
Runnable demo: `agent_query.py` — a local stand-in for AgentCore where each
`Agent` embeds its own DuckDB connection over a shared hive-partitioned Parquet
lake (local by default, S3 via `DATA_ROOT`).

Invariants (offline, self-contained):
- Each `Agent` holds an independent DuckDB connection (no shared writable file).
- Concurrent fan-out of N agents over the read-only lake returns **identical**
  results for every agent (multi-reader, no contention).
- Aggregate is correct: total event count across regions equals rows written.
- Partition-pruned read (`WHERE dt = <day>`) returns exactly that day's rows via
  `hive_partitioning=true`.
