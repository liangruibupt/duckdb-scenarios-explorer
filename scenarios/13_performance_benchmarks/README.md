# 13 — Performance benchmarks · 性能测试

> **English and 中文.** Each section gives the English text first, then the
> Chinese text. 每一节先英文，后中文。

How far does single-node DuckDB go? This scenario measures it on public,
standard workloads instead of guessing, from 10 GB to about 1 TB, plus a
579 GiB lake queried in place on S3. It backs the README section
"How much data can one query handle?".

单机 DuckDB 能处理多大的数据？本场景不靠猜，而是用公开的标准测试集实测：从 10 GB 到约 1 TB，
再加上一个在 S3 上原地查询的 579 GiB 数据湖。它为根目录 README 中“一次能处理多少数据？”一节提供实测依据。

## Benchmarks · 测试集

| Harness | Data | What it measures |
|---|---|---|
| `bench.py` | **TPC-H** SF1 / SF10 / SF100 / SF1000, generated with DuckDB's `tpch` extension | The 22 TPC-H queries on the native `.duckdb` file and on Parquet; time, peak RSS, peak buffer memory and spill per query; an extra run with a lowered `memory_limit` to force larger-than-memory execution |
| `clickbench.py` | **[ClickBench](https://github.com/ClickHouse/ClickBench)** `hits`: 100M rows, 14.8 GB Parquet | ClickBench's 43 queries, 3 runs each (cold, then best of two hot), on the Parquet file and on a DuckDB table; comparable with the public ClickBench results |
| `overture.py` | **[Overture Maps](https://docs.overturemaps.org/)** release 2026-10-21.0: 1,020 Parquet files, 579 GiB on S3 | 8 queries read straight from `s3://overturemaps-us-west-2`: footer-only counts, full-column scans, bbox filters (Seattle, Tokyo), and extracting a city to local Parquet; cold/warm time and **GB actually received over the network** |

| 脚本 | 数据 | 测什么 |
|---|---|---|
| `bench.py` | **TPC-H** SF1 / SF10 / SF100 / SF1000，用 DuckDB 的 `tpch` 扩展生成 | 22 个 TPC-H 查询，分别查原生 `.duckdb` 文件和 Parquet；记录每个查询的耗时、进程内存峰值、缓冲区内存峰值和溢写量；另外再用较低的 `memory_limit` 跑一遍，强制进入超出内存的执行 |
| `clickbench.py` | **[ClickBench](https://github.com/ClickHouse/ClickBench)** `hits`：1 亿行，Parquet 14.8 GB | ClickBench 的 43 个查询，每个跑 3 次（第一次冷启动，后两次取最快为热查询），分别查 Parquet 文件和 DuckDB 表；可与 ClickBench 公开榜单对比 |
| `overture.py` | **[Overture Maps](https://docs.overturemaps.org/)** 2026-10-21.0 版本：S3 上 1,020 个 Parquet 文件，579 GiB | 8 个直接读取 `s3://overturemaps-us-west-2` 的查询：只读文件尾的计数、整列扫描、坐标框过滤（西雅图、东京）、把一个城市导出成本地 Parquet；记录冷/热耗时，以及**实际从网络收到多少 GB** |

ClickBench's view and queries are fetched at run time from a pinned ClickBench
commit and are not copied here, because ClickBench is licensed CC BY-NC-SA 4.0.
Overture data carries its own per-theme licenses (ODbL / CDLA).

ClickBench 的视图和查询在运行时从固定的 ClickBench 提交拉取，没有复制进本仓库，因为 ClickBench 的许可证
是 CC BY-NC-SA 4.0。Overture 数据按主题各有许可证（ODbL / CDLA）。

## Run locally · 本地运行

```bash
pip install -r requirements.txt
cd scenarios/13_performance_benchmarks
python bench.py --sf 1                          # ~1 GB, seconds
python bench.py --sf 10 --source parquet        # ~10 GB raw
python bench.py --sf 100 --memory-limit 10GB    # needs ~45 GB free disk
python clickbench.py                            # downloads 14.8 GB
python overture.py                              # reads S3 in place; best run in us-west-2
```

Results go to `results/` as JSON (and Markdown for TPC-H). `run_all.sh` runs
the SF1 → SF100 ladder on one machine.

结果以 JSON 写入 `results/`（TPC-H 还会生成 Markdown）。`run_all.sh` 在一台机器上依次跑 SF1 → SF100。

## Run on EC2 · 在 EC2 上运行

`ec2/` launches one **self-terminating** instance per benchmark. The user-data
script formats the local NVMe instance store (RAID 0 when there are several
disks), clones this repo, runs the lines of a `runs_*.txt` file, prints the
results to the EC2 console log, and shuts down. The instance is launched with
shutdown behavior `terminate` and a hard time cap. It has no key pair and
needs no inbound access, SSH or SSM.

`ec2/` 为每个测试集启动一台**会自动终止**的实例。开机脚本会格式化本地 NVMe 实例存储（多块盘时组成
RAID 0），克隆本仓库，执行 `runs_*.txt` 中的每一行，把结果打印到 EC2 控制台日志，然后关机。实例以
`terminate` 关机行为和硬性时间上限启动，没有密钥对，也不需要入站访问、SSH 或 SSM。

```bash
cd scenarios/13_performance_benchmarks/ec2
./launch.sh m8gd.2xlarge  <branch> runs_sf10.txt       us-east-1 <subnet> 180
./launch.sh r8gd.4xlarge  <branch> runs_sf100.txt      us-east-1 <subnet> 300
./launch.sh r8gd.16xlarge <branch> runs_sf1000.txt     us-east-1 <subnet> 480
./launch.sh m8gd.4xlarge  <branch> runs_clickbench.txt us-east-1 <subnet> 180
./launch.sh m8gd.4xlarge  <branch> runs_overture.txt   us-west-2 <subnet> 180
./fetch_results.sh <instance-id> <region>   # copies the JSON results into ../results/
```

## Results · 结果

DuckDB 2.0.0 throughout. Times are wall-clock seconds for all queries summed.

全部使用 DuckDB 2.0.0。耗时为所有查询的总和（秒）。

"Native vs Parquet" is how much faster the same queries run on the native
`.duckdb` file than on Parquet (the percentage is the time saved). For the
`memory_limit` rows it is the slowdown against the same run without a cap.

“原生对比 Parquet”一列表示同样的查询在原生 `.duckdb` 文件上比在 Parquet 上快多少倍，括号里是节省的时间比例。
`memory_limit` 两行则表示与不限内存的同一运行相比慢了多少。

### How each column reads the data · 每一列怎么读数据

Both columns are DuckDB. They differ in the **file format** and **where the
file lives**, not in who reads it.

| Benchmark | Native `.duckdb` column | Parquet column | Network in the timed queries |
|---|---|---|---|
| TPC-H SF1–SF1000 | The `.duckdb` file `dbgen` wrote, on local NVMe | Parquet exported from that same database, on the same local NVMe, queried through views in a fresh in-memory database | None |
| ClickBench | `hits.parquet` loaded into a local `.duckdb` file first (load time reported separately) | `hits.parquet` on local NVMe, queried directly | None (the 14.8 GB download happens once, before timing) |
| Overture | Not measured | Parquet read in place from S3 with `httpfs`; only the needed columns and row groups are fetched | Yes on cold runs, none on warm runs |

So for TPC-H and ClickBench the "Native vs Parquet" ratio compares two file
formats on the same local disk. Only the Overture numbers include S3 latency
and bandwidth.

**Caching.** None of the harnesses clears caches between queries, so read the
numbers as warm rather than cold-from-disk:

| Benchmark | Runs per query | What is cached |
|---|---|---|
| TPC-H | 1 | DuckDB keeps blocks it has read in its buffer pool and reuses them in later queries; most of the native run's peak RSS (224 GB at SF1000) is these cached blocks. The files were written just before the queries, so much of them is likely still in the OS page cache, which helps both columns. The page cache is not dropped before queries. |
| ClickBench | 3 | The table reports **hot** time (best of runs 2–3), so both columns run on cached data. Cold times are in the JSON. |
| Overture | 2 | The table reports **cold** time, which includes fetching from S3. The warm run reads 0 GB over the network because DuckDB caches the remote data. |

Not dropping the page cache makes TPC-H's absolute times optimistic. Its effect
on the native-vs-Parquet ratio should be smaller, because both columns benefit,
but that has not been measured separately.

两列都是 DuckDB 在读，区别在于**文件格式**和**文件放在哪里**，不在于由谁来读。

| 测试 | 原生 `.duckdb` 列 | Parquet 列 | 计时查询中是否走网络 |
|---|---|---|---|
| TPC-H SF1–SF1000 | `dbgen` 生成的 `.duckdb` 文件，在本地 NVMe 上 | 由同一个数据库导出的 Parquet，在同一块本地 NVMe 上，在一个新的内存数据库里通过视图查询 | 不走 |
| ClickBench | 先把 `hits.parquet` 导入本地 `.duckdb` 文件（导入耗时单独记录） | 直接查本地 NVMe 上的 `hits.parquet` | 不走（14.8 GB 的下载只做一次，在计时之前） |
| Overture | 未测 | 用 `httpfs` 直接读 S3 上的 Parquet，只取需要的列和行组 | 冷查询走网络，热查询不走 |

因此，TPC-H 和 ClickBench 的“原生对比 Parquet”比较的是同一块本地盘上两种文件格式的差别。只有 Overture 的
数字包含 S3 的网络延迟和带宽。

**缓存。** 各测试脚本都没有在查询之间清空缓存，所以这些数字是热数据下的表现，不是从磁盘冷读：

| 测试 | 每个查询跑几次 | 缓存了什么 |
|---|---|---|
| TPC-H | 1 次 | DuckDB 会把读过的块留在缓冲池里，后面的查询可以复用；原生运行的内存峰值（SF1000 为 224 GB）大部分就是这些缓存块。文件在查询前刚生成或刚导出，很可能大部分还在操作系统页缓存里，两列都会因此受益。查询前没有清空页缓存。 |
| ClickBench | 3 次 | 表里是**热**时间（第 2、3 次中最快的），两列都在缓存数据上运行。冷时间在 JSON 里。 |
| Overture | 2 次 | 表里是**冷**时间，包含从 S3 拉取数据。热查询的网络读取为 0 GB，因为 DuckDB 缓存了远程数据。 |

没有清空页缓存会让 TPC-H 的绝对耗时偏乐观。对“原生对比 Parquet”倍数的影响应该较小，因为两列都受益，但这一点
没有单独测过。

| Benchmark | Machine | Native `.duckdb` | Parquet | Native vs Parquet · 原生对比 Parquet | Peak RSS (native / Parquet) | Spill |
|---|---|---:|---:|---:|---:|---:|
| TPC-H SF1 | m8g.xlarge (4 vCPU, 15 GB) | 0.6 s | 1.3 s | **2.2× faster** (−54%) | 0.34 / 0.32 GB | 0 |
| TPC-H SF10 | m8g.xlarge (4 vCPU, 15 GB) | 6.9 s | 15.2 s | **2.2× faster** (−55%) | 2.6 / 0.9 GB | 0 |
| TPC-H SF10 | m8gd.2xlarge (8 vCPU, 31 GB) | 2.9 s | 7.0 s | **2.4× faster** (−59%) | 2.7 / 1.0 GB | 0 |
| TPC-H SF100 | r8gd.4xlarge (16 vCPU, 128 GB) | 14.7 s | 36.3 s | **2.5× faster** (−60%) | 24.8 / 7.6 GB | 0 |
| TPC-H SF100, `memory_limit=16GB` | r8gd.4xlarge (16 vCPU, 128 GB) | 15.4 s | — | +5% vs no cap | 15.6 GB | 0 |
| TPC-H SF1000 | r8gd.16xlarge (64 vCPU, 512 GB) | 52.2 s | 168.9 s | **3.2× faster** (−69%) | 224 / 70 GB | 0 |
| TPC-H SF1000, `memory_limit=128GB` | r8gd.16xlarge (64 vCPU, 512 GB) | 75.8 s | — | +45% vs no cap | 123 GB | 0 |
| ClickBench (43 queries, hot) | m8gd.4xlarge (16 vCPU, 64 GB) | 10.6 s | 17.2 s | **1.6× faster** (−38%) | 24.8 / 8.0 GB | 0 |
| Overture on S3 (8 queries, cold) | m8gd.8xlarge (32 vCPU, 128 GB), us-west-2 | — | 103.2 s | — | 5.6 GB | 0 |

Observations so far: at SF10 every query fits comfortably in memory on both
machines, the native file is about 2× faster than Parquet, and doubling the
cores roughly halves the time. DuckDB's `dbgen` generates data at about the
same speed (~43 s per SF5 chunk) on 16 and 64 vCPU machines, so SF1000
generation takes about 2.4 hours regardless of instance size.

目前的观察：SF10 时两台机器上所有查询都轻松放进内存，原生文件比 Parquet 快约 2 倍，核数翻倍耗时大约
减半。DuckDB 的 `dbgen` 在 16 核和 64 核机器上生成速度几乎一样（每个 SF5 分块约 43 秒），所以无论实例
多大，生成 SF1000 都要约 2.4 小时。

**SF100 (~100 GB raw, 27 GB `.duckdb`, 22.5 GB Parquet).** All 22 queries take
14.7 s in total on the native file; the slowest single query (Q13) takes 1.7 s.
Parquet is 2.5× slower (36.3 s) but its peak RSS is a third (7.6 GB vs 24.8 GB),
because the native run keeps the database's blocks cached. Capping
`memory_limit` at 16 GB, below the 27 GB database, costs only 5% (15.4 s) and
**causes no spill**: DuckDB evicts cached blocks and re-reads them from the NVMe
disk; no query's working state came near 16 GB. Generating SF100 took 14.5 min
and exporting it to Parquet 39 s.

**ClickBench (100M rows, 13.8 GiB Parquet).** All 43 queries pass. Hot totals:
10.6 s on a DuckDB table (after a 34 s load) and 17.2 s directly on the Parquet
file, with no spill. Q28 (a `REGEXP_REPLACE` over URLs with a high-cardinality
GROUP BY) is the slowest at 3.5 s / 5.0 s. Downloading the file took 148 s.

**SF1000 (~1 TB raw, 280 GB `.duckdb`, 231 GB Parquet).** All 22 queries pass:
52.2 s in total on the native file (slowest Q13, 8.9 s) and 168.9 s on Parquet
(slowest Q18, 33.4 s), with no spill. Going from SF100 to SF1000 (10× the data, 4×
the cores) took 3.6× longer on the native file. The native run's peak RSS
(224 GB) is mostly cached database blocks: capping `memory_limit` at 128 GB, less
than half the 280 GB database, still runs every query without spilling, 45%
slower (75.8 s). Generating the data took 2.4 h (`dbgen` is close to
single-threaded) and exporting it to Parquet 2.7 min.

**SF1000（原始约 1 TB，`.duckdb` 280 GB，Parquet 231 GB）。** 22 个查询全部通过：原生文件共 52.2 秒（最慢 Q13，
8.9 秒），Parquet 共 168.9 秒（最慢 Q18，33.4 秒），都没有溢写。从 SF100 到 SF1000，数据是 10 倍、核数是 4 倍，
原生文件耗时增加到 3.6 倍。原生运行 224 GB 的内存峰值主要是缓存的数据库块：把 `memory_limit` 限制到 128 GB
（不到 280 GB 数据库的一半），所有查询仍然不溢写，只慢了 45%（75.8 秒）。生成数据用了 2.4 小时（`dbgen` 基本是
单线程），导出 Parquet 用了 2.7 分钟。

**Overture (579 GiB of Parquet on S3, read in place).** All 8 queries pass, and
no query read more than 2.1 GB over the network:

| Query | Cold | Warm | Network (cold) |
|---|---:|---:|---:|
| Count 88M places (footers only) | 0.32 s | 0.11 s | 0.04 GB |
| Top place categories (1 column, all places) | 2.96 s | 0.15 s | 0.15 GB |
| Count 2.53B buildings (footers only, 258 GiB theme) | 1.28 s | 0.70 s | 0.43 GB |
| Seattle bbox filter over all buildings | 1.23 s | 0.58 s | 0.43 GB |
| Height by subtype over all 2.53B buildings | 79.3 s | 1.16 s | 2.03 GB |
| Road segments by class (68 GiB theme) | 16.0 s | 0.38 s | 0.45 GB |
| Tokyo bbox filter over road segments | 0.67 s | 0.20 s | 0.25 GB |
| Extract Seattle's 345k buildings to local Parquet | 1.49 s | 0.74 s | 0.50 GB |

Even the full scan of every building reads 2 GB of the 258 GiB theme, because
DuckDB fetches only the needed columns, and bbox filters skip files and row
groups using their statistics. Warm runs read nothing over the network: DuckDB
caches the remote data it has already read. Peak memory stayed under 6 GB. Two
earlier attempts on smaller instances ended in an unexplained instance reboot
during the full building scan; this run isolated each query in its own process
and logged memory every 10 s, and the reboot did not recur (available memory
never dropped below 120 GB).

**Overture（S3 上 579 GiB 的 Parquet，原地读取）。** 8 个查询全部通过，没有一个查询从网络读取超过 2.1 GB：

| 查询 | 冷 | 热 | 网络读取（冷） |
|---|---:|---:|---:|
| 统计 8800 万个地点（只读文件尾） | 0.32 秒 | 0.11 秒 | 0.04 GB |
| 地点类别排行（1 列，全部地点） | 2.96 秒 | 0.15 秒 | 0.15 GB |
| 统计 25.3 亿栋建筑（只读文件尾，258 GiB） | 1.28 秒 | 0.70 秒 | 0.43 GB |
| 在全部建筑上做西雅图坐标框过滤 | 1.23 秒 | 0.58 秒 | 0.43 GB |
| 全部 25.3 亿栋建筑按类型统计高度 | 79.3 秒 | 1.16 秒 | 2.03 GB |
| 道路按类别统计（68 GiB） | 16.0 秒 | 0.38 秒 | 0.45 GB |
| 在道路上做东京坐标框过滤 | 0.67 秒 | 0.20 秒 | 0.25 GB |
| 把西雅图 34.5 万栋建筑导出为本地 Parquet | 1.49 秒 | 0.74 秒 | 0.50 GB |

即使扫描全部建筑，也只读了 258 GiB 中的 2 GB，因为 DuckDB 只取需要的列，坐标框过滤还会根据统计信息跳过
文件和行组。热查询完全不再走网络：DuckDB 会缓存已经读过的远程数据。内存峰值一直低于 6 GB。之前在较小实例上
的两次尝试都在建筑全量扫描时遇到原因不明的实例重启；这次每个查询单独一个进程，每 10 秒记录一次内存，没有再
重启（可用内存始终高于 120 GB）。

