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
Results still running are marked *pending*.

全部使用 DuckDB 2.0.0。耗时为所有查询的总和（秒）。仍在运行的标为 *pending*。

| Benchmark | Machine | Native `.duckdb` | Parquet | Peak RSS (native / Parquet) | Spill |
|---|---|---:|---:|---:|---:|
| TPC-H SF1 | m8g.xlarge (4 vCPU, 15 GB) | 0.6 s | 1.3 s | 0.34 / 0.32 GB | 0 |
| TPC-H SF10 | m8g.xlarge (4 vCPU, 15 GB) | 6.9 s | 15.2 s | 2.6 / 0.9 GB | 0 |
| TPC-H SF10 | m8gd.2xlarge (8 vCPU, 31 GB) | 2.9 s | 7.0 s | 2.7 / 1.0 GB | 0 |
| TPC-H SF100 | r8gd.4xlarge (16 vCPU, 128 GB) | 14.7 s | 36.3 s | 24.8 / 7.6 GB | 0 |
| TPC-H SF100, `memory_limit=16GB` | r8gd.4xlarge (16 vCPU, 128 GB) | 15.4 s | — | 15.6 GB | 0 |
| TPC-H SF1000 | r8gd.16xlarge (64 vCPU, 512 GB) | *pending* | *pending* | | |
| ClickBench (43 queries, hot) | m8gd.4xlarge (16 vCPU, 64 GB) | 10.6 s | 17.2 s | 24.8 / 8.0 GB | 0 |
| Overture (S3) | m8gd.4xlarge, us-west-2 | — | *rerun needed* | | |

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

**Overture.** The first run did not produce results: the instance rebooted about
two minutes into the benchmark, and user-data does not run again after a reboot.
It has to be rerun.

**SF100（原始约 100 GB，`.duckdb` 27 GB，Parquet 22.5 GB）。** 原生文件上 22 个查询共 14.7 秒，最慢的
单个查询（Q13）1.7 秒。Parquet 慢 2.5 倍（36.3 秒），但进程内存峰值只有三分之一（7.6 GB 对 24.8 GB），
因为原生运行会把数据库块缓存在内存里。把 `memory_limit` 限制到 16 GB（低于 27 GB 的数据库）只慢了 5%
（15.4 秒），而且**没有溢写**：DuckDB 会淘汰缓存的块，再从 NVMe 磁盘重新读取；没有哪个查询的工作状态接近
16 GB。生成 SF100 用了 14.5 分钟，导出为 Parquet 用了 39 秒。

**ClickBench（1 亿行，Parquet 13.8 GiB）。** 43 个查询全部通过。热查询总耗时：DuckDB 表上 10.6 秒（导入用了
34 秒），直接查 Parquet 文件 17.2 秒，都没有溢写。最慢的是 Q28（对 URL 做 `REGEXP_REPLACE` 再按高基数分组），
分别为 3.5 秒和 5.0 秒。下载文件用了 148 秒。

**Overture。** 第一次运行没有产出结果：实例在测试开始约两分钟后重启了，而 user-data 在重启后不会再次运行，
需要重跑。
