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

## When to use DuckDB (and when not to)

DuckDB is an analytical engine embedded in a process. Most of its limits come
from that design: it scales up on one machine, it is tuned for scanning many
rows rather than touching one, and in its default mode it is a library, not a
shared service. Facts below follow the DuckDB 2.0 docs
([Concurrency](https://duckdb.org/docs/2.0/connect/concurrency.html),
[Limits](https://duckdb.org/docs/2.0/operations_manual/limits.html),
[Tuning Workloads](https://duckdb.org/docs/2.0/guides/performance/how_to_tune_workloads.html)).

### 1. Limitations to know

| Area | Limitation | What to do about it |
|---|---|---|
| **Writers** | A native `.duckdb` file has **one read-write process**. Other processes can only open it with `access_mode = 'READ_ONLY'`, and not while a writer holds it. Inside the writer process, threads can write concurrently (MVCC + optimistic concurrency): appends never conflict, but two transactions updating/deleting the **same row** fail with `Transaction conflict`, and the app has to retry. | For multi-process writes, use the Quack remote protocol (client-server mode) or **DuckLake** with a PostgreSQL catalog. Or write open files (Parquet / Iceberg) and let each reader open its own DuckDB. See scenarios [03](scenarios/03_csv_to_parquet_etl/), [06](scenarios/06_log_analytics/), [07](scenarios/07_multiagent_agentcore/). |
| **Scale** | **Single node.** There is no distributed execution, so throughput is capped by one machine's cores, RAM, disk and network. | Partition the work (per tenant, per day, per agent) and run many independent DuckDB instances (scenario [07](scenarios/07_multiagent_agentcore/)). Use Spark/EMR/Athena/Redshift when one job truly needs a cluster. |
| **Memory** | `memory_limit` defaults to **80% of RAM** and covers only the buffer manager. Joins, GROUP BY and ORDER BY spill to disk (temp dir capped at 90% of free disk). Several blocking operators in one query can still hit out-of-memory, and some aggregates (`string_agg`, sort-based holistic aggregates) cannot spill. | Set `memory_limit`, `temp_directory` and `threads` explicitly, especially in containers and Lambda (2–10 GB RAM, small `/tmp`). Pre-aggregate or split very wide queries. |
| **Point access / OLTP** | Storage is columnar with ~122k-row row groups. Single-row `INSERT`/`UPDATE`/lookup at high QPS is slow compared with a row store. PRIMARY KEY/UNIQUE use ART indexes, which add write overhead. | Batch writes (Appender, `INSERT ... SELECT`, `COPY`). Keep transactional traffic in Aurora/RDS/DynamoDB and analyze a copy (scenarios [10](scenarios/10_aurora_pg_datalake/), [12](scenarios/12_dynamodb_zero_etl/)). |
| **Security model** | In-process mode has **no users, roles or GRANT**. Whoever can call the library can read every table and every file the process can reach. | Enforce access outside the engine: IAM / Lake Formation on S3, plus query rewriting for row/column rules (scenario [08](scenarios/08_governance/)). Enable `enable_external_access = false` / lock configuration when SQL comes from users or LLMs. |
| **Remote storage** | Over S3/HTTP each file costs round trips. Thousands of small files or unpartitioned data make queries slow. A native `.duckdb` file on S3 can only be attached read-only. Parquet files are immutable, so "update" means rewrite. | Compact to ~100 MB–1 GB Parquet, use Hive partitioning, and use Iceberg/DuckLake when you need updates, deletes and snapshots (scenarios [02](scenarios/02_httpfs_s3/), [09](scenarios/09_iceberg/)). |
| **Operations** | There is no built-in replication, HA or point-in-time recovery for a native file. File locking on NFS/shared drives is unreliable. Native extensions must match the platform and DuckDB version, and unsigned extensions are blocked by default. | Treat the `.duckdb` file as a rebuildable cache, or keep the source of truth in S3 (Parquet/Iceberg/DuckLake). Pin the DuckDB version and pre-install extensions in the image. |
| **Hard limits** | String/BLOB max 4 GB per value, array size 100,000, expression depth 1,000. There is no practical database file size limit (15 TB+ files are in use), but opening and checkpointing huge files gets slower. | These are rarely the bottleneck. Check them with `current_setting(...)` when in doubt. |

### 2. Good fits for DuckDB

- **Ad-hoc and exploratory analytics on files**: SQL directly over Parquet,
  CSV and JSON, locally or on S3, without loading a warehouse first
  (scenarios [01](scenarios/01_nyc_taxi/), [02](scenarios/02_httpfs_s3/)).
- **Single-node ETL/ELT**: cleaning, joining and reshaping up to roughly
  hundreds of GB per job and writing partitioned Parquet or Iceberg. This is
  often faster and cheaper than starting a Spark cluster
  (scenarios [03](scenarios/03_csv_to_parquet_etl/), [11](scenarios/11_glue_duckdb_etl/)).
- **Embedded analytics inside an application, Lambda or agent**: each process
  carries its own engine, so there is nothing to operate and no idle cost
  (scenarios [04](scenarios/04_chat_bi/), [07](scenarios/07_multiagent_agentcore/), [12](scenarios/12_dynamodb_zero_etl/)).
- **Data science workflows**: zero-copy SQL over Pandas, Polars and Arrow
  in notebooks, and feature preparation for ML
  (scenario [05](scenarios/05_sql_over_dataframes/)).
- **Log and event analysis**: percentiles, rollups and time windows over
  NDJSON/Parquet logs (scenario [06](scenarios/06_log_analytics/)).
- **Analytics next to an OLTP or lake system**: Aurora PostgreSQL's embedded
  DuckDB, DynamoDB zero-ETL to Iceberg, and reading Iceberg/DuckLake tables
  with time travel (scenarios [09](scenarios/09_iceberg/), [10](scenarios/10_aurora_pg_datalake/), [12](scenarios/12_dynamodb_zero_etl/)).
- **Testing and CI for data pipelines**: a full SQL engine in `pip install`,
  so data-quality checks and SQL unit tests run anywhere.
- **Edge and browser**: DuckDB-Wasm for client-side dashboards over a
  downloaded Parquet file.

### 3. Poor fits for DuckDB

- **High-concurrency OLTP**: order systems, account balances, many small
  transactions per second from many clients. Use Aurora/RDS, DynamoDB or
  another row store.
- **Many independent writers on one shared database file**: in-process mode
  allows one writer process. Use Quack or DuckLake only if you accept running
  a server or a catalog database. Otherwise this is a job for a server
  database.
- **A shared, multi-user enterprise warehouse with built-in RBAC, workload
  isolation and many concurrent BI users**: Redshift, Snowflake or Athena fit
  better. DuckDB can still serve as a per-user or per-agent engine on top of
  the same lake.
- **Jobs that do not fit on one machine**: multi-TB shuffles or joins with
  large intermediate state that would spill past local disk. Use Spark/EMR or
  a distributed warehouse.
- **Low-latency key-value serving**: sub-millisecond lookups by key at high
  QPS. Use DynamoDB, ElastiCache or a row-store index.
- **Continuous streaming with per-event updates**: many single-row updates
  per second against the same tables. Buffer into micro-batches, or use a
  streaming system (Kinesis/Flink/MSK) and let DuckDB query the landed files.
- **Primary system of record needing HA and replication**: a single native
  file has no replicas or failover. Keep the source of truth in a managed
  database or in S3 table formats.
- **Large-scale search and vector retrieval as the main workload**: the `fts`
  and `vss` extensions work for prototypes and moderate data, but dedicated
  engines (OpenSearch, S3 Vectors, pgvector) scale and update better.

**Rule of thumb:** if the question is "scan and aggregate many rows, mostly
read, from one process at a time", DuckDB is a strong default. If it is "many
clients changing a few rows each, all at once", put a transactional database
in front and let DuckDB analyze its data afterwards.

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
