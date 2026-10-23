# duckdb-scenarios-explorer

A growing collection of hands-on scenarios that show where **DuckDB** shines:
in-process, columnar, vectorized analytics (OLAP) over files — Parquet, CSV,
JSON, DataFrames, and remote object storage — with **no server and no load step**.

Each scenario is self-contained under `scenarios/<NN_name>/` with its own
runnable scripts. See **[SCENARIOS.md](SCENARIOS.md)** for the catalog and the
status of each one.

## Primary reference

This repo is heavily informed by the AWS reference implementation
**[aws-samples/sample-data-agent-on-duckdb](https://github.com/aws-samples/sample-data-agent-on-duckdb)**
— a governed data agent whose compute plane is DuckDB embedded *inside the agent
process*, reading open-format data directly on Amazon S3 (raw Parquet, S3 Tables
/ Iceberg, Glue, DuckLake), with identity-aware governance compiled into every
SQL statement. Our scenarios 04/07/08 (chat BI, multi-agent AgentCore, RLS/CLS +
context + semantic layers) and the Iceberg pass (02/03/06/09) mirror that
design's five layers — **compute, governance, context, semantic, scheduling/
identity** — as small, independently-runnable, spec-driven demos. When in doubt
about the "production-shaped" version of a scenario here, read that sample.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Scenario 01 — NYC taxi analytics
cd scenarios/01_nyc_taxi
./get_data.sh          # downloads ~48MB public Parquet + zone CSV (not committed)
python analytics.py    # 6 analytical queries over ~3M rows
python benchmark.py    # DuckDB vs Pandas on the same aggregate
python report.py       # -> report.html (self-contained, inline-SVG charts)
```

## Why DuckDB for these

- **No ETL to start**: query a Parquet/CSV/JSON file directly with SQL.
- **Columnar + vectorized**: reads only the columns a query touches; predicate
  and projection push-down into Parquet.
- **Embedded**: a library in your process (Python/CLI/WASM), not a service to
  operate — zero infra, zero idle cost.
- **Real SQL**: window functions, exact & approximate quantiles, `httpfs` for
  S3/HTTP, joins across heterogeneous file formats.

## Repo layout

```
scenarios/
  01_nyc_taxi/            analytics + benchmark + HTML report
  02_httpfs_s3/           query Parquet on S3 in place; raw + Iceberg access paths
  03_csv_to_parquet_etl/  CSV -> partitioned Parquet / DuckLake managed table
  04_chat_bi/             NL -> DuckDB SQL (rule-based + Bedrock hook), governed path
  05_sql_over_dataframes/ zero-copy SQL over Pandas DataFrames
  06_log_analytics/       NDJSON logs: percentiles, rollups, DuckLake time-travel
  07_multiagent_agentcore/ embedded-per-agent DuckDB + shared S3 layer (DESIGN + fan-out)
  08_governance/          RLS/CLS rewrite + cost gate + result handles + semantic + matrix
  09_iceberg/             Iceberg/DuckLake: snapshots, time-travel, CoW vs MoR, WHY_ICEBERG.md
  10_aurora_pg_datalake/  Aurora PostgreSQL embedded-DuckDB: live OLTP + Iceberg/Parquet lake in one SQL
  11_glue_duckdb_etl/     DuckDB-on-Glue 6.0 ETL -> managed Iceberg table on S3 Tables (no Spark)
  12_dynamodb_zero_etl/   DynamoDB zero-ETL -> Iceberg on S3 Tables -> DuckDB analytics (Lambda)
specs/                    per-scenario acceptance criteria (SPEC / GOVERNANCE / PIPELINE / ICEBERG / AWS_DUCKDB)
tests/                    offline / data-gated / s3-gated pytest suite (CI-run)
requirements.txt
SCENARIOS.md
```

## References

- **[aws-samples/sample-data-agent-on-duckdb](https://github.com/aws-samples/sample-data-agent-on-duckdb)**
  — the primary reference (governed DuckDB data agent on Amazon Bedrock
  AgentCore; raw Parquet / S3 Tables / Glue / DuckLake access paths).
- [Apache Iceberg spec](https://iceberg.apache.org/spec) · [evolution](https://iceberg.apache.org/docs/latest/evolution) · [reliability](https://iceberg.apache.org/docs/latest/reliability)
  — the table-format mechanism behind scenario 09 (see
  [WHY_ICEBERG.md](scenarios/09_iceberg/docs/WHY_ICEBERG.md)).

### AWS × DuckDB integrations (scenarios 10–12)

Following the DuckLabs acquisition (effective 2026-09-01), AWS is embedding
DuckDB across its data services. These scenarios mirror three such launches as
self-contained offline demos + a real cloud script each (see
[specs/AWS_DUCKDB_SPEC.md](specs/AWS_DUCKDB_SPEC.md)):

- **[Aurora PostgreSQL now queries Iceberg/Parquet directly](https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/)**
  (embedded DuckDB, GA 2026-09-30) — scenario 10.
- **[Cost-effective ETL with DuckDB and S3 Tables on AWS Glue](https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue)**
  (Glue 6.0, 2026-10-06) — scenario 11.
- **[Run DuckDB analytics on your DynamoDB data with zero-ETL](https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/)**
  (2026-09-11) — scenario 12.
