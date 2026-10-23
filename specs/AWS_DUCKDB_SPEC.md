# AWS × DuckDB integration pass — spec

Three scenarios tracking AWS's late-2026 push to embed DuckDB across its data
services (following the DuckLabs acquisition, effective 2026-09-01). Each is a
self-contained OFFLINE demo + test (CI-run) plus a cloud script that runs the
real AWS flow when env vars point at live resources. AI-DLC contract for `tests/`.

Source announcements:
- **10** — Aurora PostgreSQL direct data-lake query (embedded DuckDB), **GA
  2026-09-30**:
  https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/
- **11** — Cost-effective ETL with DuckDB + S3 Tables on AWS Glue 6.0
  (**2026-10-06**):
  https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue
- **12** — Run DuckDB analytics on DynamoDB data with zero-ETL (**2026-09-11**):
  https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/

Design rule (same as the Iceberg pass): offline demos use DuckDB directly, with
**DuckLake** as the local Iceberg-style stand-in where a managed table is needed;
the cloud scripts use the real service (Aurora `aurora_analytics`, S3 Tables
Iceberg REST catalog). The transform/query SQL is identical on both paths — that
portability (develop+test in CI, deploy unchanged) is the point.

## Test tiers
- **offline**: always run — flattening/transform correctness, managed-table
  snapshots + time-travel, the unified-query shape. CI-run.
- **cloud-gated**: the `cloud_*.py` scripts; exercised only with live AWS
  resources + env vars (not wired into the default pytest run).

---

## 10 — Aurora PostgreSQL + embedded-DuckDB data-lake query (NEW)
`scenarios/10_aurora_pg_datalake/`

- `datalake_query.py` — offline stand-in: one embedded DuckDB UNIONs a small
  operational table (`recent_transactions`, last 7 days) with a large Parquet
  "lake" (`transaction_history`, 5 years), and JOINs live rows to a lake-derived
  per-category historical average — the exact shape Aurora runs under
  `aurora_analytics`, minus Postgres. `seed()` sizes are parameterized for tests.
- `cloud_aurora.py` — the real flow: `CREATE EXTENSION aurora_analytics`,
  `CREATE FOREIGN TABLE … ()` (empty column list ⇒ schema auto-read), the unified
  UNION query, and `aurora_analytics_stat_statements()`. Needs psycopg + PG* env
  + an IAM role with the `AuroraAnalytics` feature on an Aurora PG 17.11+/18.6+
  cluster.

Invariants (offline): the lake side is larger than the OLTP side; the recent
window spans ≤ 6 days; the UNION contributes rows from BOTH branches for a
customer present on both sides; the timeline respects `LIMIT 15` and date-DESC
order; every enriched live row matches a historical average and `delta = amount −
hist_avg`.

## 11 — DuckDB-on-Glue 6.0 ETL to S3 Tables Iceberg (NEW)
`scenarios/11_glue_duckdb_etl/`

- `glue_etl.py` — offline: a shared `transform_sql()` (clean/cast/compute
  revenue) run as two "job runs" that CREATE then INSERT into a DuckLake managed
  table — each append a snapshot, time-travellable. This is the SQL you deploy to
  a Glue 6.0 Python-shell job unchanged.
- `cloud_glue_s3tables.py` — imports the SAME `transform_sql()` and runs it
  against a real S3 Tables Iceberg table (ATTACH the REST catalog, CREATE on
  first run / INSERT after). No Spark cluster.

Invariants (offline): the transform is subtractive (drops bad units / blank store
/ unparsable rows); every landed row is valid; `revenue = round(units·price, 2)`;
each job run is a new snapshot and the table grows; time-travel to the run-1
snapshot yields day-1 rows only; store/category are lowercased+trimmed.

## 12 — DynamoDB zero-ETL → Iceberg on S3 Tables → DuckDB (NEW)
`scenarios/12_dynamodb_zero_etl/`

- `ddb_analytics.py` — offline: synthesize DynamoDB items WITH type descriptors
  (`{"S":…}` / `{"N":…}`), model the zero-ETL **flattening** (unwrap descriptors
  to native typed values, lowercase attribute names — `PK`→`pk`), land them in a
  DuckLake managed table, then run the blog's revenue-by-category query plus
  order-volume-by-hour and status-mix.
- `cloud_ddb_lambda.py` — attach the real zero-ETL S3 Tables catalog READ_ONLY
  with the AWS sample's exact DuckDB lockdown (`disabled_filesystems`,
  `lock_configuration`, no community extensions) — usable as a local client or as
  the DuckDB-in-Lambda handler body behind an IAM function URL.

Invariants (offline): synthesized items are single-key type descriptors;
flattening unwraps to native numbers/strings and lowercases names (no `PK`, no
`{"N":…}` left); an integral `N` becomes `int`; the landed table is typed
(numeric `amount`, integer `items`, varchar `category`); per-category revenues
sum to the table total (no rows dropped); analytical queries use plain columns
(no attribute unwrapping in SQL).
