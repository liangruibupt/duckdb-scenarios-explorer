# Scenarios · 场景目录

> **English and 中文.** Each section gives the English text first, then the
> Chinese text. 每一节先英文，后中文。

Status legend: ✅ implemented · 🧪 proposed / next · 💡 idea

状态说明：✅ 已实现 · 🧪 已提议 / 下一步 · 💡 想法

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
| 10 | **Aurora PostgreSQL data-lake query (embedded DuckDB)** | AWS GA 2026-09-30: DuckDB embedded *inside Aurora* unions live OLTP rows with Iceberg/Parquet in S3 in one SQL, no reverse-ETL; offline stand-in + real `aurora_analytics` flow | ✅ implemented + tested |
| 11 | **DuckDB-on-Glue 6.0 ETL → S3 Tables Iceberg** | DuckDB as the Glue 6.0 transform engine (no Spark): clean/cast → append to a managed Iceberg table (snapshots + time-travel); same SQL offline (DuckLake) and on S3 Tables | ✅ implemented + tested |
| 12 | **DynamoDB zero-ETL → Iceberg → DuckDB** | Zero-ETL replicates DynamoDB (via PITR) into Iceberg on S3 Tables; DuckDB serves analytics in a Lambda; models the attribute-flattening + a read-only engine lockdown | ✅ implemented + tested |
| 13 | **Performance benchmarks (TPC-H SF1–SF1000, ClickBench, Overture on S3)** | Measured single-node limits: 22 TPC-H queries from 1 GB to ~1 TB on native file vs Parquet, forced spill with a low `memory_limit`, ClickBench's 43 queries, and a 579 GiB S3 lake queried in place; self-terminating EC2 runners | ✅ implemented + measured |

| # | 场景 | 展示的 DuckDB 能力 | 状态 |
|---|------|--------------------|------|
| 01 | **纽约出租车分析** | 不导入、直接查询 300 万行 Parquet；窗口函数、分位数、关联 CSV 维表；DuckDB 与 Pandas 基准对比；HTML 报告 | ✅ 已实现 |
| 02 | **httpfs / S3 远程 Parquet** | 不下载、直接查询 S3/HTTP 上的 Parquet；分区裁剪；Hive 分区通配路径 | ✅ 已实现 |
| 03 | **CSV → Parquet ETL** | 把 DuckDB 当作轻量 ETL 引擎：给脏 CSV 定类型并清洗，`COPY ... TO` 写出分区 Parquet，再查询 | ✅ 已实现 |
| 04 | **对话式 BI（自然语言 → SQL）** | 自然语言问题 → 基于 Parquet 的 DuckDB SQL；规则规划器 + Bedrock 大模型接口；DuckDB 作为即席 OLAP 加速器 | ✅ 已实现 |
| 05 | **对 Pandas DataFrame 做 SQL** | 对内存中的 DataFrame 做零拷贝 SQL；在 notebook 中混用 Python 和 SQL | ✅ 已实现 |
| 06 | **日志 / 可观测性分析** | 读取 NDJSON/CSV 日志，计算 p50/p95/p99 延迟、错误率、按时间桶汇总 | ✅ 已实现 |
| 07 | **AgentCore 上的多智能体 OLAP** | 每个智能体内嵌 DuckDB + 共享只读数据层（Parquet，以及 S3 Tables 上的 Iceberg）；在本地和真实托管 Iceberg 表上都验证了多读者并发扇出与分区裁剪 | ✅ 已实现 + [DESIGN.md](scenarios/07_multiagent_agentcore/DESIGN.md) |
| 08 | **带治理的数据智能体（RLS/CLS + 上下文 + 语义层）** | 基于 sqlglot 的 RLS/CLS 改写（失败即拒绝）+ 成本闸门 + 结果句柄 + 历史压缩 + 治理→成本→执行流水线 + 注册指标语义层；已接入 chat_bi | ✅ 已实现 + 已测试 |
| 09 | **Iceberg / DuckLake 表格式** | ACID 快照、时间旅行（`AT VERSION`）、模式演进、行级 UPDATE/DELETE，这些是原始 Parquet 做不到的；本地用 DuckLake，云端用 `iceberg_scan`（S3 Tables） | ✅ 已实现 + 已测试 |
| 10 | **Aurora PostgreSQL 数据湖查询（内嵌 DuckDB）** | AWS 2026-09-30 GA：*Aurora 内部*嵌入的 DuckDB 在一条 SQL 里把实时 OLTP 行与 S3 上的 Iceberg/Parquet 做 UNION，无需反向 ETL；离线替身 + 真实 `aurora_analytics` 流程 | ✅ 已实现 + 已测试 |
| 11 | **Glue 6.0 上的 DuckDB ETL → S3 Tables Iceberg** | DuckDB 作为 Glue 6.0 的转换引擎（无需 Spark）：清洗/转换类型 → 追加写入托管 Iceberg 表（快照 + 时间旅行）；同一份 SQL 可离线跑（DuckLake），也可在 S3 Tables 上跑 | ✅ 已实现 + 已测试 |
| 12 | **DynamoDB 零 ETL → Iceberg → DuckDB** | 零 ETL 把 DynamoDB（通过 PITR）复制为 S3 Tables 上的 Iceberg；DuckDB 在 Lambda 中提供分析；模拟属性扁平化 + 只读引擎锁定 | ✅ 已实现 + 已测试 |
| 13 | **性能测试（TPC-H SF1–SF1000、ClickBench、S3 上的 Overture）** | 实测单机边界：TPC-H 22 个查询从 1 GB 到约 1 TB，对比原生文件与 Parquet；用较低的 `memory_limit` 强制溢写；ClickBench 43 个查询；在 S3 上原地查询 579 GiB 数据湖；自动终止的 EC2 运行脚本 | ✅ 已实现 + 已实测 |

---

## 01 — NYC Taxi analytics · 纽约出租车分析 ✅

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

- `get_data.sh`：下载 2024 年 1 月黄色出租车 Parquet（约 48MB，296 万行）和区域对照 CSV。
- `analytics.py`：6 个分析查询，包括数据集概览、按小时的收入/小费、行程距离分位数（精确值 +
  `approx_quantile`）、最繁忙的上车区域（Parquet ⨝ CSV）、支付方式占比（窗口函数）、每日 7 天
  移动平均、机场行程的收入情况。
- `benchmark.py`：同一个按小时分组的聚合，分别用 DuckDB 和 Pandas 执行。结果：**DuckDB 约快
  2.5 倍**（5 次取最好：77ms 对 195ms），而且从不把全部 19 列读进内存。
- `report.py`：输出一个自包含的 `report.html`，图表为内嵌 SVG（不依赖绘图库）。

主要发现（2024 年 1 月）：296 万行清洗后剩 272 万行；小费比例在下午 6 点达到峰值约 20.7%；JFK 是
收入最高的上车区域（1110 万美元）；83.5% 的行程用卡支付，其中 95% 给了小费，而现金行程记录的小费
都是 0 美元（一个数据质量陷阱）。

## 02 — httpfs / S3 remote Parquet · httpfs / S3 远程 Parquet ✅

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

- `remote_parquet.py`：`INSTALL httpfs; LOAD httpfs;` 加上一个 `credential_chain` 类型的 S3
  secret，然后 `read_parquet('s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/…')`：统计行数、在 S3 上
  下推一个只涉及 3 列的聚合、对 `year=/month=` 做 Hive 分区裁剪。脚本会自动检测：对象存在时直接
  查询，否则打印上传命令后退出。
- `seed_s3.sh`：一次性上传脚本（请在有 S3 写权限的终端里运行；Kiro Crew 智能体被禁止写 S3），
  把本地出租车 Parquet 按 Hive 分区布局上传到存储桶。

动机：原地查询数据湖，不下载、不需要集群，只为扫描的字节付费。每个智能体内嵌 DuckDB 用的就是这种模式。

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

- `etl.py`：完全自包含。先合成一个故意弄脏的 CSV（大小写混杂、空字段、带引号的千位分隔符、
  一行垃圾数据、错误的数量值），然后 `read_csv(ignore_errors=true)` → 清洗/转换类型（`try_cast`、
  `trim`、`lower`、去掉 `,`）→ `COPY … TO (FORMAT parquet, PARTITION_BY (dt), COMPRESSION zstd)`
  → 再把输出查回来。
- 已验证：50,001 行原始数据 → 41,599 行干净数据（丢弃 8,402 行），7 个按天分区，
  **CSV 2.70 MB → Parquet 0.34 MB（缩小 7.9 倍）**。小批量/流式可放在 Lambda 里跑，大批量可放在
  Fargate 任务里跑。

## 04 — Chat BI (NL → SQL) · 对话式 BI（自然语言 → SQL） ✅

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

- `chat_bi.py`：英文问题 → 针对出租车 Parquet 的 DuckDB SQL → 答案 + 一个小型内嵌柱状图，不用手写
  SQL。自然语言→SQL 这一层**可插拔**：默认是确定性的离线**规则规划器**（不需要 API key，适合 CI），
  另有一个**大模型规划器接口**（`llm_plan`，Bedrock Converse），对开放式问题加了只允许只读 SELECT
  的护栏。`--repl` 进入交互模式，也可以把问题作为参数传入。
- 离线验证：“how many trips” → 2,869,697；“busiest 5 zones”、“avg tip by hour”、“payment mix”、
  “revenue by day” 都生成了正确的 SQL 和图表。

架构（来自讨论）：自然语言→DuckDB→S3 上的 Parquet 是成本最低的起点；只有数据超出单节点时才加
Athena，只有需要受治理的指标时才加语义层（Cube/dbt），不要叠加多余的引擎。

## 05 — SQL over Pandas DataFrames · 对 Pandas DataFrame 做 SQL ✅

`scenarios/05_sql_over_dataframes/`

- `sql_over_df.py` — DuckDB queries an in-memory Pandas DataFrame **by variable
  name** with no copy and no load step: aggregate over a DataFrame, DataFrame ⨝
  DataFrame, a window function (share-of-customer + rank), a DataFrame ⨝
  Parquet-on-disk join in one query, and the result handed back as both Pandas
  (`.df()`) and Arrow (`.arrow()`). Self-contained (builds its own frames; the
  Parquet join uses scenario 01's taxi file if present).
- The point: stay in Python, reach for SQL exactly where Pandas gets awkward.

- `sql_over_df.py`：DuckDB **按变量名**直接查询内存中的 Pandas DataFrame，不拷贝、不导入：对
  DataFrame 聚合、DataFrame ⨝ DataFrame、窗口函数（客户占比 + 排名）、在一个查询里把 DataFrame 与
  磁盘上的 Parquet 关联，结果同时以 Pandas（`.df()`）和 Arrow（`.arrow()`）返回。自包含（自己构造
  DataFrame；如果场景 01 的出租车文件存在，就用它做 Parquet 关联）。
- 要点：留在 Python 里，只在 Pandas 写起来别扭的地方改用 SQL。

## 06 — Log / observability analytics · 日志 / 可观测性分析 ✅

`scenarios/06_log_analytics/`

- `log_analytics.py` — self-contained. Synthesizes a realistic NDJSON access log
  (200k lines, per-endpoint latency/error profiles, an injected 14:10–14:13
  latency spike), then `read_json_auto` + SQL: **p50/p95/p99 latency per
  endpoint** (`approx_quantile`), **4xx/5xx error rate per endpoint**,
  **per-minute `time_bucket` rollup** (the spike surfaces at ~550ms p95 vs ~140ms
  baseline), and an overall SLO summary.
- The point: native NDJSON analytics with no parse/ETL step and no log service —
  the pattern for ad-hoc "why was it slow at 14:03?" over a log dump on disk/S3.

- `log_analytics.py`：自包含。先合成一份接近真实的 NDJSON 访问日志（20 万行，每个接口有各自的
  延迟/错误分布，并在 14:10–14:13 注入一次延迟尖峰），然后 `read_json_auto` + SQL：**每个接口的
  p50/p95/p99 延迟**（`approx_quantile`）、**每个接口的 4xx/5xx 错误率**、**按分钟 `time_bucket`
  汇总**（尖峰期 p95 约 550ms，基线约 140ms），以及整体 SLO 汇总。
- 要点：原生分析 NDJSON，无需解析/ETL，也无需日志服务。适合对磁盘或 S3 上的日志转储即席回答
  “14:03 为什么慢？”这类问题。

## 07 — Multi-agent OLAP on AgentCore · AgentCore 上的多智能体 OLAP ✅ (implemented + design · 已实现 + 设计)

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

`scenarios/07_multiagent_agentcore/` 包含设计文档 `DESIGN.md`（调研 → 规划 → 实现 → 测试）和可运行
演示 `agent_query.py`：每个 `Agent` 内嵌自己的 DuckDB 连接，读取同一个按 Hive 分区的 Parquet 数据湖；
`fan_out()` 并发运行 N 个智能体，证明它们返回相同结果且互不争用（多读者），另有一个按天分区裁剪的
读取。默认使用本地数据湖（离线/CI），也可以用 `DATA_ROOT=s3://bucket/prefix` 指向 S3。
建议：**每个智能体内嵌 DuckDB** + 通过 `httpfs` 读取 **S3 上按 Hive 分区的 Parquet**，而不是共享
一个 DuckDB 服务。写入走 OLTP（Aurora），或走单写者追加 Parquet 的路径。只有超过单节点规模时才加
Athena；只有需要受治理的指标时才加语义层。

## 08 — Governed data agent: RLS/CLS + context layer · 带治理的数据智能体：RLS/CLS + 上下文层 ✅

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

把 `aws-samples/sample-data-agent-on-duckdb` 中的两层搬过来，它们把一个朴素的自然语言→SQL 工具
变成一个*受治理的*智能体。规格：`specs/GOVERNANCE_SPEC.md`。

- `governance.py`：用 sqlglot 在**进入引擎之前**做基于身份的 **RLS/CLS 改写**，失败即拒绝：未知身份
  默认拒绝一切；RLS `row_filter` 以 AND 加到每一个表引用上；被禁止的列从 `SELECT *` 中 `EXCLUDE`，
  被显式点名时**直接干净地拒绝**；表白名单；只允许 SELECT 的语句形态白名单（藏在 `WITH` 前缀后的
  DML 也会被拒）；CTE 不能遮蔽受治理的表；所有角色都禁止访问主机资源的路径。
- `context.py`：**成本闸门**（对分区原始数据源的查询，如果没有分区列上的过滤条件就拒绝；分区跨度过宽
  也拒绝）、**绑定所有者的结果句柄**（超过 `MAX_RESULT_ROWS` 的结果变成会话临时表 `_r_<n>`；别人的
  句柄在进入引擎前就被拒绝），以及**历史压缩**（模型上下文超过 `COMPRESSION_THRESHOLD` 后，旧的
  结果数据块变成一行指针；当前轮不受影响）。
- 测试：42 个离线测试，包括一个**角色 × 语句形态治理矩阵**，期望结果由策略推导（admin 原样通过，
  analyst 在每种形态上都被加上 RLS+CLS，junior 被禁止的列在每种形态上都被拒绝）。
- `pipeline.py`：一次调用（`run_statement`）完成**治理 → 成本 → 执行 + 结果整形**；成本闸门和引擎
  看到的是治理后的 SQL（而不是原始 SQL），拒绝时会指出是哪个阶段，每条语句都产生一条审计记录。
- `semantic.py`：**注册指标层**，`Registry` + `Metric`；按名称调用指标，只能使用白名单内的维度/时间，
  确定性地编译为一条受治理的 `SELECT`，并走同一条流水线（所以 RLS/CLS 和成本闸门依然生效）。未注册
  的指标或白名单外的维度会被拒绝，不允许临时拼 SQL。
- 已通过 `--principal tenant:role` 接入 `scenarios/04_chat_bi/chat_bi.py`，演示问题会走受治理的路径；
  默认路径不变。

## 09 — Iceberg / DuckLake table format · Iceberg / DuckLake 表格式 ✅

`scenarios/09_iceberg/tables.py` — proves the capabilities a raw Parquet glob
cannot give, offline via **DuckLake** (a local read/write Iceberg-style format:
SQL catalog + Parquet data): **ACID snapshots**, **time-travel**
(`… AT (VERSION => n)`), **schema evolution** (`ALTER TABLE … ADD COLUMN`, old
snapshots still read), and **row-level UPDATE/DELETE**. The cloud analogue is
Amazon S3 Tables (Iceberg REST), read via the `iceberg` extension's
`iceberg_scan`. Spec: `specs/ICEBERG_SPEC.md`.

`scenarios/09_iceberg/tables.py` 离线证明原始 Parquet 通配路径做不到的能力，使用 **DuckLake**（一种
本地可读写的 Iceberg 风格格式：SQL 目录 + Parquet 数据）：**ACID 快照**、**时间旅行**
（`… AT (VERSION => n)`）、**模式演进**（`ALTER TABLE … ADD COLUMN`，旧快照仍可读取）以及
**行级 UPDATE/DELETE**。云端对应的是 Amazon S3 Tables（Iceberg REST），通过 `iceberg` 扩展的
`iceberg_scan` 读取。规格：`specs/ICEBERG_SPEC.md`。

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

**对已有场景做的 Iceberg 改造**（同一份规格）：
- **02**：在原始通配路径旁边增加 Iceberg 访问路径（`iceberg_scan`，`S3_TABLES_ICEBERG=…`），
  对应 aws-sample 的路径 A/路径 B。
- **03**：DuckLake 托管表作为 ETL 目标（`etl.py --target ducklake`）：两次追加 → 两个快照，每个
  都能时间旅行。
- **06**：DuckLake 日志模式（`log_analytics.py --ducklake`）：先追加尖峰前的时间窗口，再追加尖峰
  窗口，各成一个快照，然后用时间旅行回答“14:10 尖峰之前表是什么样？”。
- **07**：更新了 DESIGN.md，只要有智能体写入，共享只读层就应该是 S3 上的 Iceberg 表（ACID + 快照
  隔离），而不是原始通配路径。
- **08**：治理矩阵增加 `iceberg` 访问路径一列；在每条路径上改写结果都相同（基于名称，与格式无关），
  75/75 个单元格通过。

Engine note (DuckDB 1.5.5): `iceberg` is a reader (`iceberg_scan`,
`iceberg_snapshots`); `ducklake` is the read/write format used for the offline
differentiator demos.

引擎说明（DuckDB 1.5.5）：`iceberg` 是读取器（`iceberg_scan`、`iceberg_snapshots`）；`ducklake`
是离线差异化演示所用的可读写格式。

### Why it works (mechanism, with real output) · 为什么可行（机制与真实输出）

See **[docs/WHY_ICEBERG.md](scenarios/09_iceberg/docs/WHY_ICEBERG.md)** — the
*why* behind each capability: Iceberg is an atomically-swappable, stat-carrying
metadata layer over immutable Parquet files. Runnable demonstrations:
- `principles.py` — real output for each of the four principles: time-travel
  (current 999 vs AS-OF 200), schema evolution (4 cols now vs 3 in the old
  snapshot), pushdown pruning, and a row-level delete whose **file signature**
  (`delete_files 0→1`, data files unchanged) shows merge-on-read.
- `cow_vs_mor.py` — copy-on-write vs merge-on-read by observable signature, and
  how to choose (CoW for read-heavy, MoR for write/upsert-heavy + compaction).
- `pruning_benchmark.py` — metadata pruning vs a raw-Parquet glob's O(files)
  LIST; honest about local disk hiding the gap and where the real S3 win is.

见 **[docs/WHY_ICEBERG.md](scenarios/09_iceberg/docs/WHY_ICEBERG.md)**，解释每项能力背后的原因：
Iceberg 是一层建立在不可变 Parquet 文件之上、可原子替换、携带统计信息的元数据。可运行的演示：
- `principles.py`：四个原理各自的真实输出，包括时间旅行（当前 999 行对比历史时点 200 行）、模式演进
  （现在 4 列，旧快照 3 列）、下推裁剪，以及一次行级删除，其**文件特征**（`delete_files 0→1`，数据
  文件不变）说明这是 merge-on-read。
- `cow_vs_mor.py`：通过可观察的文件特征区分 copy-on-write 和 merge-on-read，并说明如何选择（读多用
  CoW，写多/upsert 多用 MoR 并配合合并）。
- `pruning_benchmark.py`：元数据裁剪对比原始 Parquet 通配路径 O(文件数) 的 LIST 开销；如实说明本地
  磁盘会掩盖差距，真正的收益出现在 S3 上。

### Learning point — DuckLake managed-table vs Amazon S3 Tables · 学习要点：DuckLake 托管表与 Amazon S3 Tables

Both are **Iceberg-style table formats** (a catalog + snapshots + ACID on top of
Parquet files). They differ in *where the catalog lives and who operates it* —
this repo uses DuckLake as the **offline stand-in** and S3 Tables as the **live
cloud** table, so the same concepts are provable in CI and demonstrated for real.

两者都是 **Iceberg 风格的表格式**（在 Parquet 文件之上加目录 + 快照 + ACID）。区别在于*目录放在哪里、
由谁运维*。本仓库用 DuckLake 作为**离线替身**，用 S3 Tables 作为**真实的云端**表，这样同样的概念既能
在 CI 中证明，也能在真实环境中演示。

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

| | **DuckLake** | **Amazon S3 Tables** |
|---|---|---|
| 目录 | 本地 SQL 数据库文件（`*.ducklake`） | AWS 托管的 **Iceberg REST** 目录 |
| 数据文件 | 本地磁盘（或 S3）上的 Parquet | S3 Tables 存储桶中的 Parquet |
| 运行位置 | 进程内、**离线**、不需要 AWS | AWS 服务（需要账号） |
| 表格式 | DuckLake 自有格式（朝兼容 Iceberg 的方向发展） | **Apache Iceberg**（标准） |
| 从 DuckDB 写入 | `CREATE`/`INSERT`/`UPDATE`/`DELETE`/`ALTER` | 通过 REST 目录 `CREATE TABLE AS` + `INSERT`（以追加为主）；对裸元数据位置用 `iceberg_scan` 只能读 |
| 维护 | 自己合并文件 | AWS 自动合并 |
| 多引擎 | 目前以 DuckDB 为中心 | 任何 Iceberg 读取器（Athena、Spark、Trino、DuckDB） |
| 成本 | 免费 | S3 Tables 存储 + 维护费用 |
| 本仓库中用于 | 离线差异化演示 + CI（09/03/06 测试） | 真实表（`09/cloud_s3tables.py`、`02` 路径 B） |

Rule of thumb: **DuckLake** to prove the *capabilities* cheaply and offline;
**S3 Tables** when you want a real, multi-engine, AWS-managed Iceberg table that
Athena/Spark/Trino can also read. Same query, same governance (scenario 08's
matrix proves the rewrite is identical across raw/s3t/glue/dl/iceberg paths);
only how the table name resolves to files differs.

经验法则：用 **DuckLake** 低成本、离线地证明*能力*；需要一张真实的、多引擎可读、由 AWS 托管、
Athena/Spark/Trino 也能读的 Iceberg 表时，用 **S3 Tables**。查询相同，治理相同（场景 08 的矩阵证明在
raw/s3t/glue/dl/iceberg 各路径上改写结果一致），不同的只是表名如何解析到文件。

## 10 — Aurora PostgreSQL data-lake query (embedded DuckDB) · Aurora PostgreSQL 数据湖查询（内嵌 DuckDB） ✅

`scenarios/10_aurora_pg_datalake/` · spec: `specs/AWS_DUCKDB_SPEC.md`

On **2026-09-30** AWS made DuckDB embedded *inside Amazon Aurora PostgreSQL* GA
(17.11+/18.6+): query live operational rows (incl. uncommitted writes) together
with Apache Iceberg/Parquet in S3, S3 Tables, or the Glue Data Catalog — in one
PostgreSQL statement, no reverse-ETL
([announcement](https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/)).

- `datalake_query.py` — **offline stand-in**: one embedded DuckDB UNIONs a small
  `recent_transactions` table (last 7 days, the OLTP "hot" side) with a 5-year
  Parquet `transaction_history` "lake", and JOINs live rows to a lake-derived
  per-category historical average (the "enrich a transaction with context" use
  case). Self-contained; `seed()` sizes are parameterized for fast tests.
- `cloud_aurora.py` — the **real** flow against an Aurora cluster:
  `CREATE EXTENSION aurora_analytics`, `CREATE FOREIGN TABLE … ()` (empty column
  list ⇒ Aurora auto-reads the schema from Parquet/Iceberg metadata), the unified
  UNION query, and per-query stats via `aurora_analytics_stat_statements()`.
  Needs psycopg + `PG*` env + an IAM role carrying the `AuroraAnalytics` feature.
- Tests: 6 offline invariants (lake bigger than OLTP; 7-day window; UNION spans
  both branches; `LIMIT 15` + date-DESC order; enrichment `delta = amount −
  hist_avg`).

The point: the reverse-ETL pipeline that used to copy history into the OLTP
database is gone — Aurora runs this exact DuckDB engine under the hood.

**2026-09-30**，AWS 正式发布*内嵌在 Amazon Aurora PostgreSQL 中*的 DuckDB（17.11+/18.6+）：在一条
PostgreSQL 语句里，同时查询实时业务数据（包括未提交的写入）以及 S3、S3 Tables 或 Glue Data Catalog
中的 Apache Iceberg/Parquet，无需反向 ETL
（[发布公告](https://aws.amazon.com/blogs/aws/amazon-aurora-postgresql-now-supports-direct-querying-of-apache-iceberg-and-parquet-data-in-your-data-lake/)）。

- `datalake_query.py`：**离线替身**，一个内嵌 DuckDB 把一张小的 `recent_transactions` 表（最近 7 天，
  OLTP 的“热”数据）与 5 年的 Parquet `transaction_history`“数据湖” UNION 起来，并把实时数据与从
  数据湖算出的各品类历史均值 JOIN（“用上下文丰富一笔交易”的用例）。自包含；`seed()` 的数据量可
  参数化，以便快速测试。
- `cloud_aurora.py`：针对 Aurora 集群的**真实**流程：`CREATE EXTENSION aurora_analytics`、
  `CREATE FOREIGN TABLE … ()`（列表为空 ⇒ Aurora 自动从 Parquet/Iceberg 元数据读取表结构）、统一的
  UNION 查询，以及通过 `aurora_analytics_stat_statements()` 查看每个查询的统计。需要 psycopg、`PG*`
  环境变量，以及带有 `AuroraAnalytics` 功能的 IAM 角色。
- 测试：6 个离线不变量（数据湖比 OLTP 大；7 天窗口；UNION 覆盖两个分支；`LIMIT 15` + 按日期降序；
  丰富字段 `delta = amount − hist_avg`）。

要点：过去把历史数据复制进 OLTP 数据库的反向 ETL 管道不再需要，Aurora 底层运行的就是这个 DuckDB 引擎。

## 11 — DuckDB-on-Glue 6.0 ETL → S3 Tables Iceberg · Glue 6.0 上的 DuckDB ETL → S3 Tables Iceberg ✅

`scenarios/11_glue_duckdb_etl/` · spec: `specs/AWS_DUCKDB_SPEC.md`

AWS's Oct-2026 guidance: for scheduled SQL transforms, **DuckDB on AWS Glue 6.0**
is a lightweight, low-cost alternative to a Spark cluster
([article](https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue)).

- `glue_etl.py` — **offline**: a shared `transform_sql()` (clean/cast/compute
  `revenue`) run as two "job runs" that CREATE then INSERT into a **DuckLake**
  managed table — each append its own snapshot, time-travellable. The same SQL
  you deploy to Glue unchanged.
- `cloud_glue_s3tables.py` — imports the **same** `transform_sql()` and runs it
  against a real **S3 Tables** Iceberg table (ATTACH the REST catalog; CREATE on
  first run, INSERT after). No Spark; S3 Tables auto-compacts.
- Tests: 6 offline invariants (subtractive clean; `revenue = round(units·price)`;
  one snapshot per run; time-travel to run-1 = day-1 rows; normalized text).

Portability is the point: develop and CI-test the job's SQL locally, deploy the
identical SQL to a single Glue 6.0 worker.

AWS 2026 年 10 月的建议：对于定时执行的 SQL 转换，**AWS Glue 6.0 上的 DuckDB** 是 Spark 集群的轻量、
低成本替代方案
（[文章](https://aws-news.com/article/2026-10-06-cost-effective-etl-with-duckdb-and-amazon-s3-tables-on-aws-glue)）。

- `glue_etl.py`：**离线**，一个共享的 `transform_sql()`（清洗/转换类型/计算 `revenue`）作为两次
  “作业运行”执行，先 CREATE 再 INSERT 到 **DuckLake** 托管表，每次追加形成一个快照，可以时间旅行。
  这就是原样部署到 Glue 的那份 SQL。
- `cloud_glue_s3tables.py`：导入**同一个** `transform_sql()`，在真实的 **S3 Tables** Iceberg 表上
  运行（ATTACH REST 目录；首次运行 CREATE，之后 INSERT）。不需要 Spark；S3 Tables 自动合并文件。
- 测试：6 个离线不变量（清洗只删不增；`revenue = round(units·price)`；每次运行一个快照；时间旅行到
  第 1 次运行 = 第 1 天的行；文本已规范化）。

要点是可移植性：在本地开发并用 CI 测试作业的 SQL，再把完全相同的 SQL 部署到单个 Glue 6.0 worker。

## 12 — DynamoDB zero-ETL → Iceberg → DuckDB · DynamoDB 零 ETL → Iceberg → DuckDB ✅

`scenarios/12_dynamodb_zero_etl/` · spec: `specs/AWS_DUCKDB_SPEC.md`

A **zero-ETL** integration replicates a DynamoDB table (from PITR backups, so the
table is unaffected) into Iceberg on **S3 Tables** on a refresh interval; a
DuckDB-in-Lambda function serves ad-hoc SQL over it behind an IAM function URL
([blog](https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/)).

- `ddb_analytics.py` — **offline**: synthesize DynamoDB items *with* type
  descriptors (`{"S":…}` / `{"N":…}`), model the zero-ETL **flattening** (unwrap
  to native typed values; lowercase names — `PK`→`pk`), land them in a DuckLake
  managed table, then run the blog's revenue-by-category query + order-volume-by-
  hour + status-mix.
- `cloud_ddb_lambda.py` — attach the real zero-ETL S3 Tables catalog `READ_ONLY`
  with the AWS sample's **exact DuckDB lockdown** (`disabled_filesystems`,
  `lock_configuration`, no community extensions). Works as a local client or as
  the Lambda handler body. Deploy the integration from
  [aws-dynamodb-examples/…/ddb-duckdb-analytics](https://github.com/aws-samples/aws-dynamodb-examples/tree/master/infrastructure_as_code/cdk/ddb-duckdb-analytics).
- Tests: 7 offline invariants (descriptors unwrapped; names lowercased; integral
  `N`→`int`; typed landed columns; per-category revenue sums to the total).

The operational table keeps serving single-digit-ms traffic; analytics run on the
replicated Iceberg copy — the same copy Athena/Redshift/EMR/Spark can also read.

**零 ETL** 集成按刷新间隔把 DynamoDB 表（从 PITR 备份复制，因此不影响原表）复制为 **S3 Tables** 上的
Iceberg；一个运行 DuckDB 的 Lambda 函数通过 IAM 认证的函数 URL 提供即席 SQL
（[博客](https://aws.amazon.com/blogs/database/run-duckdb-analytics-on-your-amazon-dynamodb-data-with-zero-etl/)）。

- `ddb_analytics.py`：**离线**，合成*带*类型描述符的 DynamoDB 条目（`{"S":…}` / `{"N":…}`），模拟
  零 ETL 的**扁平化**（解包为原生类型值；名称转小写，`PK`→`pk`），写入 DuckLake 托管表，然后运行博客
  里的按品类收入查询 + 按小时订单量 + 状态占比。
- `cloud_ddb_lambda.py`：以 `READ_ONLY` 挂载真实的零 ETL S3 Tables 目录，并使用 AWS 示例中
  **完全相同的 DuckDB 锁定配置**（`disabled_filesystems`、`lock_configuration`、不加载社区扩展）。
  可作为本地客户端，也可作为 Lambda 处理函数主体。集成部署见
  [aws-dynamodb-examples/…/ddb-duckdb-analytics](https://github.com/aws-samples/aws-dynamodb-examples/tree/master/infrastructure_as_code/cdk/ddb-duckdb-analytics)。
- 测试：7 个离线不变量（描述符已解包；名称已转小写；整数型 `N`→`int`；落地列带类型；各品类收入之和
  等于总收入）。

业务表继续服务个位数毫秒级的流量；分析在复制出的 Iceberg 副本上运行，Athena/Redshift/EMR/Spark
也能读取同一份副本。

## 13 — Performance benchmarks · 性能测试 ✅

`scenarios/13_performance_benchmarks/` · details and results: [README.md](scenarios/13_performance_benchmarks/README.md)

- `bench.py` — TPC-H at any scale factor via the `tpch` extension (chunked
  `dbgen` so SF100+ fits small machines), the 22 queries on the native file or on
  Parquet views, per-query time / peak RSS / buffer memory / spill, row counts
  checked against `tpch_answers()` where reference answers exist (SF ≤ 1).
- `clickbench.py` — ClickBench `hits` (100M rows, 14.8 GB), 43 queries × 3 runs on
  Parquet and on a DuckDB table; view and queries fetched from a pinned ClickBench
  commit (CC BY-NC-SA, not vendored).
- `overture.py` — 8 queries over the 579 GiB Overture Maps release read in place
  from S3, recording the GB actually received over the network;
  `overture_diag.py` runs each query in its own process and logs memory and
  kernel messages.
- `ec2/` — one self-terminating instance per benchmark: NVMe setup, run list,
  results printed to the console log, `fetch_results.sh` to collect them.
- Tests: 9 offline (tiny-SF TPC-H on both sources with answer checks, ClickBench
  view rewriting and summary, Overture query rendering).

Results (DuckDB 2.0.0, every query passed, no spill in any run):

| Benchmark | Machine | Native `.duckdb` | Parquet |
|---|---|---:|---:|
| TPC-H SF10 (22 queries) | m8gd.2xlarge, 8 vCPU / 31 GB | 2.9 s | 7.0 s |
| TPC-H SF100 | r8gd.4xlarge, 16 vCPU / 128 GB | 14.7 s | 36.3 s |
| TPC-H SF1000 (~1 TB raw, 280 GB file) | r8gd.16xlarge, 64 vCPU / 512 GB | 52.2 s | 168.9 s |
| ClickBench (43 queries, hot) | m8gd.4xlarge, 16 vCPU / 64 GB | 10.6 s | 17.2 s |
| Overture, 579 GiB on S3 (8 queries, cold) | m8gd.8xlarge, 32 vCPU / 128 GB | — | 103.2 s |

Capping `memory_limit` below the database size (16 GB at SF100, 128 GB at
SF1000) still ran every query without spilling, 5% and 45% slower. On Overture
no query read more than 2.1 GB over the network, including a full scan of all
2.53B buildings. Full numbers and analysis: the
[scenario README](scenarios/13_performance_benchmarks/README.md).

- `bench.py`：通过 `tpch` 扩展生成任意规模的 TPC-H（分块 `dbgen`，SF100 以上也能在小机器上生成），在原生
  文件或 Parquet 视图上跑 22 个查询，记录每个查询的耗时、进程内存峰值、缓冲区内存和溢写量；有参考答案时
  （SF ≤ 1）用 `tpch_answers()` 核对行数。
- `clickbench.py`：ClickBench `hits`（1 亿行，14.8 GB），43 个查询各跑 3 次，分别查 Parquet 和 DuckDB 表；视图
  和查询从固定的 ClickBench 提交拉取（CC BY-NC-SA，不复制进仓库）。
- `overture.py`：对 579 GiB 的 Overture Maps 版本在 S3 上原地执行 8 个查询，记录实际从网络收到的 GB 数；
  `overture_diag.py` 让每个查询单独一个进程运行，并记录内存和内核日志。
- `ec2/`：每个测试集一台会自动终止的实例：配置 NVMe、执行运行列表、把结果打印到控制台日志，用
  `fetch_results.sh` 取回。
- 测试：9 个离线测试（极小规模 TPC-H，两种数据源，带答案核对；ClickBench 视图改写与汇总；Overture 查询渲染）。

结果（DuckDB 2.0.0，所有查询都通过，所有运行都没有溢写）：

| 测试 | 机器 | 原生 `.duckdb` | Parquet |
|---|---|---:|---:|
| TPC-H SF10（22 个查询） | m8gd.2xlarge，8 vCPU / 31 GB | 2.9 秒 | 7.0 秒 |
| TPC-H SF100 | r8gd.4xlarge，16 vCPU / 128 GB | 14.7 秒 | 36.3 秒 |
| TPC-H SF1000（原始约 1 TB，文件 280 GB） | r8gd.16xlarge，64 vCPU / 512 GB | 52.2 秒 | 168.9 秒 |
| ClickBench（43 个查询，热） | m8gd.4xlarge，16 vCPU / 64 GB | 10.6 秒 | 17.2 秒 |
| Overture，S3 上 579 GiB（8 个查询，冷） | m8gd.8xlarge，32 vCPU / 128 GB | — | 103.2 秒 |

把 `memory_limit` 设得比数据库还小（SF100 设 16 GB，SF1000 设 128 GB），所有查询仍然不溢写，分别只慢 5% 和
45%。Overture 上没有一个查询从网络读取超过 2.1 GB，包括对全部 25.3 亿栋建筑的全量扫描。完整数据和分析见
[场景 README](scenarios/13_performance_benchmarks/README.md)。
