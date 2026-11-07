# duckdb-scenarios-explorer

> **English and 中文.** Each section gives the English text first, then the
> Chinese text. 每一节先英文，后中文。

A growing collection of hands-on scenarios that show where **DuckDB** shines:
in-process, columnar, vectorized analytics (OLAP) over files — Parquet, CSV,
JSON, DataFrames, and remote object storage — with **no server and no load step**.

Each scenario is self-contained under `scenarios/<NN_name>/` with its own
runnable scripts. See **[SCENARIOS.md](SCENARIOS.md)** for the catalog and the
status of each one.

一组持续增加的动手场景，展示 **DuckDB** 擅长的地方：在进程内运行、列式、向量化的分析
（OLAP），直接查询文件（Parquet、CSV、JSON、DataFrame 和远程对象存储），**不需要服务器，
也不需要先导入数据**。

每个场景都独立放在 `scenarios/<NN_name>/` 下，带有可直接运行的脚本。场景目录和各自的状态见
**[SCENARIOS.md](SCENARIOS.md)**。

## Primary reference · 主要参考

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

本仓库大量参考了 AWS 的参考实现
**[aws-samples/sample-data-agent-on-duckdb](https://github.com/aws-samples/sample-data-agent-on-duckdb)**。
它是一个带治理的数据智能体：计算层是**嵌入在智能体进程内**的 DuckDB，直接读取 Amazon S3 上的
开放格式数据（原始 Parquet、S3 Tables / Iceberg、Glue、DuckLake），并把基于身份的治理规则编译
进每一条 SQL。本仓库的场景 04/07/08（对话式 BI、AgentCore 多智能体、RLS/CLS + 上下文层 + 语义层）
以及 Iceberg 系列（02/03/06/09）对应该设计的五层：**计算、治理、上下文、语义、调度/身份**，
做成小而独立、按规格驱动、可单独运行的演示。想了解某个场景的“生产级”形态时，请阅读该示例。

## Quick start · 快速开始

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Scenario 01 — NYC taxi analytics / 场景 01：纽约出租车分析
cd scenarios/01_nyc_taxi
./get_data.sh          # downloads ~48MB public Parquet + zone CSV (not committed) / 下载约 48MB 公开数据（不入库）
python analytics.py    # 6 analytical queries over ~3M rows / 在约 300 万行上运行 6 个分析查询
python benchmark.py    # DuckDB vs Pandas on the same aggregate / 同一聚合下 DuckDB 与 Pandas 对比
python report.py       # -> report.html (self-contained, inline-SVG charts) / 生成自包含的 HTML 报告
```

## Why DuckDB for these · 为什么用 DuckDB

- **No ETL to start**: query a Parquet/CSV/JSON file directly with SQL.
- **Columnar + vectorized**: reads only the columns a query touches; predicate
  and projection push-down into Parquet.
- **Embedded**: a library in your process (Python/CLI/WASM), not a service to
  operate — zero infra, zero idle cost.
- **Real SQL**: window functions, exact & approximate quantiles, `httpfs` for
  S3/HTTP, joins across heterogeneous file formats.

- **无需 ETL 即可开始**：直接用 SQL 查询 Parquet/CSV/JSON 文件。
- **列式 + 向量化**：只读取查询用到的列；谓词和投影下推到 Parquet。
- **嵌入式**：作为库运行在你的进程里（Python/CLI/WASM），不是需要运维的服务，没有基础设施，
  空闲时没有成本。
- **完整的 SQL**：窗口函数、精确与近似分位数、通过 `httpfs` 访问 S3/HTTP、跨不同文件格式的 JOIN。

## When to use DuckDB (and when not to) · 什么时候用 DuckDB，什么时候不用

DuckDB is an analytical engine embedded in a process. Most of its limits come
from that design: it scales up on one machine, it is tuned for scanning many
rows rather than touching one, and in its default mode it is a library, not a
shared service. Facts below follow the DuckDB 2.0 docs
([Concurrency](https://duckdb.org/docs/2.0/connect/concurrency.html),
[Limits](https://duckdb.org/docs/2.0/operations_manual/limits.html),
[Tuning Workloads](https://duckdb.org/docs/2.0/guides/performance/how_to_tune_workloads.html)).

DuckDB 是嵌入在进程内的分析引擎，它的大部分限制都来自这个设计：只能在一台机器上纵向扩展；
优化目标是扫描大量行，而不是操作单行；默认模式下它是一个库，而不是共享服务。以下内容依据
DuckDB 2.0 文档（[Concurrency](https://duckdb.org/docs/2.0/connect/concurrency.html)、
[Limits](https://duckdb.org/docs/2.0/operations_manual/limits.html)、
[Tuning Workloads](https://duckdb.org/docs/2.0/guides/performance/how_to_tune_workloads.html)）。

### 1. Limitations to know · 需要了解的限制

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

| 方面 | 限制 | 应对方法 |
|---|---|---|
| **写入方** | 一个原生 `.duckdb` 文件同时只能有**一个读写进程**。其他进程只能用 `access_mode = 'READ_ONLY'` 打开，而且在写进程持有文件时也打不开。在写进程内部，多个线程可以并发写入（MVCC + 乐观并发控制）：追加写永远不冲突，但两个事务同时更新/删除**同一行**时，后者会报 `Transaction conflict`，需要应用重试。 | 多进程写入可用 Quack 远程协议（客户端-服务器模式），或用 PostgreSQL 作为目录库的 **DuckLake**。也可以写开放格式文件（Parquet / Iceberg），让每个读取方各自打开 DuckDB。见场景 [03](scenarios/03_csv_to_parquet_etl/)、[06](scenarios/06_log_analytics/)、[07](scenarios/07_multiagent_agentcore/)。 |
| **规模** | **单节点**，没有分布式执行，吞吐受限于一台机器的 CPU 核数、内存、磁盘和网络。 | 按租户、按天、按智能体拆分任务，运行多个相互独立的 DuckDB 实例（场景 [07](scenarios/07_multiagent_agentcore/)）。单个作业确实需要集群时，用 Spark/EMR/Athena/Redshift。 |
| **内存** | `memory_limit` 默认是**内存的 80%**，且只约束缓冲区管理器。JOIN、GROUP BY 和 ORDER BY 可以溢写到磁盘（临时目录上限为可用磁盘的 90%）。但一个查询里有多个阻塞算子时仍可能内存不足，部分聚合（`string_agg`、基于排序的整体聚合）无法溢写。 | 显式设置 `memory_limit`、`temp_directory` 和 `threads`，尤其是在容器和 Lambda 中（2–10 GB 内存，`/tmp` 空间小）。对很宽的查询先预聚合或拆分。 |
| **点查 / OLTP** | 列式存储，行组约 12.2 万行。高 QPS 的单行 `INSERT`/`UPDATE`/查找比行存数据库慢。PRIMARY KEY/UNIQUE 使用 ART 索引，会增加写入开销。 | 批量写入（Appender、`INSERT ... SELECT`、`COPY`）。事务流量放在 Aurora/RDS/DynamoDB，分析其副本（场景 [10](scenarios/10_aurora_pg_datalake/)、[12](scenarios/12_dynamodb_zero_etl/)）。 |
| **安全模型** | 进程内模式**没有用户、角色和 GRANT**。能调用这个库的代码可以读取所有表，以及进程能访问的所有文件。 | 在引擎之外做访问控制：S3 上用 IAM / Lake Formation，再加上按行/列规则改写查询（场景 [08](scenarios/08_governance/)）。当 SQL 来自用户或大模型时，设置 `enable_external_access = false` 并锁定配置。 |
| **远程存储** | 通过 S3/HTTP 访问时，每个文件都有网络往返开销。成千上万个小文件或未分区的数据会让查询变慢。S3 上的原生 `.duckdb` 文件只能以只读方式挂载。Parquet 文件不可修改，“更新”意味着重写。 | 把文件合并到约 100 MB–1 GB，使用 Hive 分区；需要更新、删除和快照时使用 Iceberg/DuckLake（场景 [02](scenarios/02_httpfs_s3/)、[09](scenarios/09_iceberg/)）。 |
| **运维** | 原生文件没有内置复制、高可用或按时间点恢复。NFS/共享盘上的文件锁不可靠。原生扩展必须与平台和 DuckDB 版本匹配，未签名扩展默认禁止加载。 | 把 `.duckdb` 文件当作可重建的缓存，或者把权威数据放在 S3（Parquet/Iceberg/DuckLake）。固定 DuckDB 版本，并在镜像中预装扩展。 |
| **硬性上限** | 单个字符串/BLOB 最大 4 GB，数组最多 100,000 个元素，表达式深度 1,000。数据库文件大小没有实际上限（已有 15 TB+ 的文件在使用），但打开和 checkpoint 超大文件会变慢。 | 这些很少成为瓶颈。不确定时用 `current_setting(...)` 查看。 |

### 2. Good fits for DuckDB · 适合 DuckDB 的场景

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

- **对文件做即席/探索式分析**：在本地或 S3 上直接用 SQL 查询 Parquet、CSV 和 JSON，不必先导入
  数据仓库（场景 [01](scenarios/01_nyc_taxi/)、[02](scenarios/02_httpfs_s3/)）。
- **单节点 ETL/ELT**：每个作业清洗、关联、重塑大约几百 GB 以内的数据，写出分区 Parquet 或
  Iceberg。通常比启动 Spark 集群更快、更便宜（场景 [03](scenarios/03_csv_to_parquet_etl/)、
  [11](scenarios/11_glue_duckdb_etl/)）。
- **嵌入到应用、Lambda 或智能体中的分析**：每个进程自带引擎，无需运维，空闲无成本（场景
  [04](scenarios/04_chat_bi/)、[07](scenarios/07_multiagent_agentcore/)、[12](scenarios/12_dynamodb_zero_etl/)）。
- **数据科学工作流**：在 notebook 中对 Pandas、Polars、Arrow 做零拷贝 SQL，以及为机器学习准备特征
  （场景 [05](scenarios/05_sql_over_dataframes/)）。
- **日志与事件分析**：对 NDJSON/Parquet 日志计算分位数、汇总和时间窗口
  （场景 [06](scenarios/06_log_analytics/)）。
- **与 OLTP 或数据湖配合的分析**：Aurora PostgreSQL 内嵌的 DuckDB、DynamoDB 零 ETL 到 Iceberg、
  读取 Iceberg/DuckLake 表并使用时间旅行（场景 [09](scenarios/09_iceberg/)、
  [10](scenarios/10_aurora_pg_datalake/)、[12](scenarios/12_dynamodb_zero_etl/)）。
- **数据管道的测试与 CI**：`pip install` 就得到完整的 SQL 引擎，数据质量检查和 SQL 单元测试在哪里都能跑。
- **边缘端与浏览器**：用 DuckDB-Wasm 在客户端对下载的 Parquet 文件做看板。

### 3. Poor fits for DuckDB · 不适合 DuckDB 的场景

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

- **高并发 OLTP**：订单系统、账户余额，以及大量客户端每秒发起的许多小事务。请用 Aurora/RDS、
  DynamoDB 或其他行存数据库。
- **多个独立写入方共享同一个数据库文件**：进程内模式只允许一个写进程。只有在你接受运行一个服务器
  或目录数据库时，才用 Quack 或 DuckLake；否则这是服务器型数据库的工作。
- **共享的多用户企业数据仓库**，需要内置 RBAC、负载隔离和大量并发 BI 用户：Redshift、Snowflake
  或 Athena 更合适。DuckDB 仍可以在同一个数据湖之上，作为每个用户或每个智能体各自的引擎。
- **一台机器放不下的作业**：数 TB 的 shuffle，或中间状态大到溢写超出本地磁盘的 JOIN。请用
  Spark/EMR 或分布式数据仓库。
- **低延迟键值服务**：高 QPS 下亚毫秒级按键查询。请用 DynamoDB、ElastiCache 或行存索引。
- **逐事件更新的持续流处理**：每秒对同一批表做大量单行更新。先缓冲成微批，或者用流处理系统
  （Kinesis/Flink/MSK），再让 DuckDB 查询落地后的文件。
- **需要高可用和复制的主记录系统**：单个原生文件没有副本和故障切换。把权威数据放在托管数据库或
  S3 表格式中。
- **以大规模全文检索和向量检索为主的负载**：`fts` 和 `vss` 扩展适合原型和中等数据量，但专用引擎
  （OpenSearch、S3 Vectors、pgvector）在规模和更新上更好。

**经验法则**：如果问题是“扫描并聚合大量行、以读为主、同一时间只有一个进程”，DuckDB 是很好的
默认选择。如果是“很多客户端同时各改几行”，就在前面放一个事务型数据库，再让 DuckDB 分析它的数据。

### 4. How much data can one query handle? · 一次能处理多少数据？

There is **no official size cap** such as "10 GB" or "100 GB". Whether DuckDB
stays fast depends on four things: how many bytes a query actually reads, how
large its intermediate state gets, how much RAM and local disk the machine
has, and I/O bandwidth.

**What the docs say**
([Working with Huge Databases](https://duckdb.org/docs/2.0/guides/performance/working_with_huge_databases.html),
[Limits](https://duckdb.org/docs/2.0/operations_manual/limits.html)):
- A native database file has no practical size limit. In the 2024 user survey,
  1% of users had files of 2 TB or more (roughly 10 TB of CSV).
- Huge files cost time to open and to checkpoint. For example, adding a few rows
  to a TPC-H SF1000 database and checkpointing takes about 5 seconds. For large
  data the docs recommend DuckLake, which spreads data over many Parquet files.
- When memory runs out, JOIN, GROUP BY and ORDER BY spill to disk. A query with
  several blocking operators, or with an aggregate that cannot spill such as
  `string_agg`, can still run out of memory.

**Measure bytes read, not total data size.** Parquet is compressed and columnar,
so 1 TB of CSV is often a fraction of that as Parquet. A query that uses 3 of 50
columns reads only those 3. Partition and statistics pruning skip most files when
the query filters on a date or partition column. A query on a "1 TB lake" may
scan only tens of GB.

**Then look at the query shape, relative to RAM:**

| Situation | Behavior |
|---|---|
| Bytes scanned fit in RAM | Runs fully in memory, fastest |
| Scan is several to tens of times RAM, mostly scan / filter / low-cardinality aggregate | Streams with little memory; time grows roughly linearly with data and is bound by I/O bandwidth |
| Big-table JOIN, high-cardinality GROUP BY, full sort or large window, with intermediate state above RAM | Spills to disk: slower but usually finishes. Needs fast local NVMe and enough temp space (default cap: 90% of free disk) |
| Intermediate state does not fit even on local disk, or the job needs a TB-scale shuffle | Not a single-node job: use Spark/EMR, Athena or Redshift |

**I/O is often the real bottleneck.** Reading from S3 is limited by one
instance's network bandwidth, typically a few GB/s, so scanning 1 TB takes
minutes, and the network is the slow part, not DuckDB. Lambda gives at most
10 GB of memory, limited `/tmp` and 15 minutes per invocation, so it suits
queries over a few GB to tens of GB that are mostly scan and aggregate.

**Rough guide** (common experience, not an official number): on a machine with
64–128 GB RAM and NVMe, scanning and aggregating a few hundred GB of Parquet is
usually smooth. TB-scale data is workable when partition and column pruning
reduce each query to a few hundred GB. Switch to a distributed engine when large
JOIN or sort intermediates stay at TB scale. The thresholds move up with bigger
machines (instances with hundreds of GB of RAM).

**Measure it.** On the target instance type, set `memory_limit` and
`temp_directory`, run your real top-N queries, and use `EXPLAIN ANALYZE` to see
time and spill.

DuckDB 没有“10GB 以内”或“100GB 以内”这类**官方上限**。能不能高效处理，取决于四件事：查询实际读多少
字节、中间状态有多大、机器有多少内存和本地磁盘，以及 I/O 带宽。

**官方的说法**
（[Working with Huge Databases](https://duckdb.org/docs/2.0/guides/performance/working_with_huge_databases.html)、
[Limits](https://duckdb.org/docs/2.0/operations_manual/limits.html)）：
- 原生数据库文件没有实际的大小限制。2024 年的用户调查里，1% 的用户在用 2 TB 以上的文件，大约相当于
  10 TB CSV。
- 超大文件的代价是打开和 checkpoint 变慢。例如在 TPC-H SF1000 库上加几行再 checkpoint，大约要 5 秒。
  文档建议大数据量改用 DuckLake，也就是把数据分散到许多 Parquet 文件里。
- 内存不够时，JOIN、GROUP BY、ORDER BY 会溢写到磁盘。但一个查询里有多个阻塞算子，或者用到
  `string_agg` 这类不能溢写的聚合时，仍然可能内存不足。

**看“查询实际读多少”，不看“数据总量”。** Parquet 是列式压缩的，1 TB 的 CSV 转成 Parquet 往往只有它的
几分之一。一张 50 列的表，查询只用 3 列，就只读这 3 列。带上日期或分区过滤条件时，分区和统计信息裁剪
可以跳过大部分文件。“1 TB 的数据湖”上的一个查询，实际可能只扫几十 GB。

**再看查询形态，以内存为参照：**

| 情况 | 表现 |
|---|---|
| 实际扫描量不超过内存 | 全在内存里跑，最快 |
| 扫描量是内存的数倍到数十倍，查询以扫描、过滤、低基数聚合为主 | 流式处理，内存占用小，耗时大致随数据量线性增长，主要受 I/O 带宽限制 |
| 大表 JOIN 大表、高基数 GROUP BY、全量排序、大窗口函数，中间状态超过内存 | 会溢写到磁盘，变慢但通常能跑完。需要快速的本地 NVMe 和足够的临时空间（默认上限是可用磁盘的 90%） |
| 中间状态连本地磁盘都放不下，或需要 TB 级 shuffle | 不适合单机，换 Spark/EMR、Athena 或 Redshift |

**I/O 也常常是瓶颈。** 从 S3 读数据时，速度受单台实例网卡带宽限制，一般在每秒几 GB 量级。扫 1 TB 要以
分钟计，这时慢在网络，不在 DuckDB 本身。Lambda 最多 10 GB 内存，`/tmp` 空间有限，单次最长 15 分钟，
更适合每次处理几 GB 到几十 GB、以扫描聚合为主的查询。

**经验参考**（常见经验，不是官方数字）：在一台 64–128 GB 内存、带 NVMe 的机器上，几百 GB 的 Parquet
做扫描和聚合通常很顺畅。TB 级数据如果查询能靠分区和列裁剪减到几百 GB 以内，也可行。只有当大 JOIN 或
排序的中间结果持续在 TB 级时，才明显该换分布式引擎。机器更大，这些边界也跟着上移，例如内存几百 GB 的
大实例。

**最可靠的办法是实测**：在目标机型上设好 `memory_limit` 和 `temp_directory`，拿真实的 Top-N 查询跑
一遍，用 `EXPLAIN ANALYZE` 看耗时和溢写量。

## Repo layout · 仓库结构

```
scenarios/
  01_nyc_taxi/            analytics + benchmark + HTML report
                          分析 + 基准测试 + HTML 报告
  02_httpfs_s3/           query Parquet on S3 in place; raw + Iceberg access paths
                          原地查询 S3 上的 Parquet；原始文件与 Iceberg 两种访问路径
  03_csv_to_parquet_etl/  CSV -> partitioned Parquet / DuckLake managed table
                          CSV -> 分区 Parquet / DuckLake 托管表
  04_chat_bi/             NL -> DuckDB SQL (rule-based + Bedrock hook), governed path
                          自然语言 -> DuckDB SQL（规则 + Bedrock 接口），带治理路径
  05_sql_over_dataframes/ zero-copy SQL over Pandas DataFrames
                          对 Pandas DataFrame 做零拷贝 SQL
  06_log_analytics/       NDJSON logs: percentiles, rollups, DuckLake time-travel
                          NDJSON 日志：分位数、汇总、DuckLake 时间旅行
  07_multiagent_agentcore/ embedded-per-agent DuckDB + shared S3 layer (DESIGN + fan-out)
                          每个智能体内嵌 DuckDB + 共享 S3 数据层（设计文档 + 并发扇出）
  08_governance/          RLS/CLS rewrite + cost gate + result handles + semantic + matrix
                          RLS/CLS 改写 + 成本闸门 + 结果句柄 + 语义层 + 测试矩阵
  09_iceberg/             Iceberg/DuckLake: snapshots, time-travel, CoW vs MoR, WHY_ICEBERG.md
                          Iceberg/DuckLake：快照、时间旅行、CoW 与 MoR、WHY_ICEBERG.md
  10_aurora_pg_datalake/  Aurora PostgreSQL embedded-DuckDB: live OLTP + Iceberg/Parquet lake in one SQL
                          Aurora PostgreSQL 内嵌 DuckDB：一条 SQL 同时查实时 OLTP 与 Iceberg/Parquet 数据湖
  11_glue_duckdb_etl/     DuckDB-on-Glue 6.0 ETL -> managed Iceberg table on S3 Tables (no Spark)
                          Glue 6.0 上的 DuckDB ETL -> S3 Tables 托管 Iceberg 表（无需 Spark）
  12_dynamodb_zero_etl/   DynamoDB zero-ETL -> Iceberg on S3 Tables -> DuckDB analytics (Lambda)
                          DynamoDB 零 ETL -> S3 Tables 上的 Iceberg -> DuckDB 分析（Lambda）
specs/                    per-scenario acceptance criteria (SPEC / GOVERNANCE / PIPELINE / ICEBERG / AWS_DUCKDB)
                          各场景验收标准
tests/                    offline / data-gated / s3-gated pytest suite (CI-run)
                          离线 / 依赖数据 / 依赖 S3 的 pytest 测试（CI 运行）
requirements.txt
SCENARIOS.md
```

## References · 参考资料

- **[aws-samples/sample-data-agent-on-duckdb](https://github.com/aws-samples/sample-data-agent-on-duckdb)**
  — the primary reference (governed DuckDB data agent on Amazon Bedrock
  AgentCore; raw Parquet / S3 Tables / Glue / DuckLake access paths).
  主要参考：运行在 Amazon Bedrock AgentCore 上、带治理的 DuckDB 数据智能体，支持原始 Parquet /
  S3 Tables / Glue / DuckLake 访问路径。
- [Apache Iceberg spec](https://iceberg.apache.org/spec) · [evolution](https://iceberg.apache.org/docs/latest/evolution) · [reliability](https://iceberg.apache.org/docs/latest/reliability)
  — the table-format mechanism behind scenario 09 (see
  [WHY_ICEBERG.md](scenarios/09_iceberg/docs/WHY_ICEBERG.md)).
  场景 09 背后的表格式机制（见 [WHY_ICEBERG.md](scenarios/09_iceberg/docs/WHY_ICEBERG.md)）。

### AWS × DuckDB integrations (scenarios 10–12) · AWS × DuckDB 集成（场景 10–12）

Following the DuckLabs acquisition (effective 2026-09-01), AWS is embedding
DuckDB across its data services. These scenarios mirror three such launches as
self-contained offline demos + a real cloud script each (see
[specs/AWS_DUCKDB_SPEC.md](specs/AWS_DUCKDB_SPEC.md)):

收购 DuckLabs（2026-09-01 生效）之后，AWS 正在把 DuckDB 嵌入到各项数据服务中。以下场景对应其中
三项发布，每个都有一个自包含的离线演示和一个真实的云端脚本（见
[specs/AWS_DUCKDB_SPEC.md](specs/AWS_DUCKDB_SPEC.md)）：

- **[Aurora PostgreSQL now queries Iceberg/Parquet directly](https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/)**
  (embedded DuckDB, GA 2026-09-30) — scenario 10.
  Aurora PostgreSQL 直接查询 Iceberg/Parquet（内嵌 DuckDB，2026-09-30 GA）：场景 10。
- **[Cost-effective ETL with DuckDB and S3 Tables on AWS Glue](https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue)**
  (Glue 6.0, 2026-10-06) — scenario 11.
  在 AWS Glue 上用 DuckDB 和 S3 Tables 做低成本 ETL（Glue 6.0，2026-10-06）：场景 11。
- **[Run DuckDB analytics on your DynamoDB data with zero-ETL](https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/)**
  (2026-09-11) — scenario 12.
  通过零 ETL 用 DuckDB 分析 DynamoDB 数据（2026-09-11）：场景 12。
