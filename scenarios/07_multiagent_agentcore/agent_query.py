#!/usr/bin/env python3
"""
Scenario 07 (implementation) -- Multi-agent OLAP with embedded DuckDB.

Embodies the design in DESIGN.md: each "agent" embeds its OWN in-process DuckDB
connection and reads a SHARED, hive-partitioned Parquet dataset in place. Many
agents read CONCURRENTLY with no contention because the data is read-only Parquet
(on local disk here, or S3 via httpfs) -- there is no shared writable DuckDB file.

This is a faithful local stand-in for AgentCore Runtime: each agent = one process
with its own embedded engine; the shared layer = partitioned Parquet.

Run:
  python agent_query.py            # builds a local hive-partitioned dataset, then
                                   # fans out N concurrent agents and shows results
  DATA_ROOT=s3://bucket/prefix python agent_query.py   # point at S3 instead
"""
from __future__ import annotations
import concurrent.futures as cf
import os
import pathlib
import duckdb

# Local shared dataset (hive-partitioned) built on demand; override with S3.
DEFAULT_ROOT = str(pathlib.Path(__file__).parent / "shared_lake" / "events")
DATA_ROOT = os.environ.get("DATA_ROOT", DEFAULT_ROOT)


def build_local_lake(root: str, days: int = 6, per_day: int = 20_000) -> None:
    """Write a hive-partitioned Parquet dataset (dt=YYYY-MM-DD/part.parquet)."""
    con = duckdb.connect()
    con.execute(f"""
        COPY (
          SELECT (i % {per_day})                                   AS event_id,
                 DATE '2024-01-01' + (i // {per_day})::INTEGER     AS dt,
                 (i % 5) + 1                                       AS region_id,
                 round((random() * 500)::DECIMAL(10,2), 2)         AS amount
          FROM range({days * per_day}) t(i)
        ) TO '{root}' (FORMAT parquet, PARTITION_BY (dt),
                       COMPRESSION zstd, OVERWRITE_OR_IGNORE true)
    """)


def glob_for(root: str) -> str:
    # S3 root -> recursive glob; local dir -> recursive glob too.
    return f"{root}/**/*.parquet"


class Agent:
    """One agent = one embedded DuckDB connection over the shared Parquet lake.
    Nothing is shared between agents except the read-only data itself."""

    def __init__(self, agent_id: int, root: str):
        self.agent_id = agent_id
        self.root = root
        self.con = duckdb.connect()          # its OWN in-process engine
        if root.startswith("s3://"):
            self.con.execute("INSTALL httpfs; LOAD httpfs;")
            self.con.execute("CREATE OR REPLACE SECRET s3 "
                             "(TYPE s3, PROVIDER credential_chain, REGION 'us-east-1');")

    def revenue_by_region(self) -> dict:
        g = glob_for(self.root)
        rows = self.con.execute(f"""
            SELECT region_id, count(*) n, round(sum(amount),2) revenue
            FROM read_parquet('{g}') GROUP BY region_id ORDER BY region_id
        """).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    def one_day(self, day: str) -> int:
        """Partition-pruned read: only the dt=<day> partition is scanned."""
        g = glob_for(self.root)
        return self.con.execute(f"""
            SELECT count(*) FROM read_parquet('{g}', hive_partitioning=true)
            WHERE dt = DATE '{day}'
        """).fetchone()[0]


def fan_out(root: str, n_agents: int = 8) -> list[dict]:
    """Run N agents concurrently against the shared lake (multi-reader)."""
    def work(i):
        return Agent(i, root).revenue_by_region()
    with cf.ThreadPoolExecutor(max_workers=n_agents) as ex:
        return list(ex.map(work, range(n_agents)))


def main() -> None:
    if not DATA_ROOT.startswith("s3://"):
        os.makedirs(pathlib.Path(DATA_ROOT).parent, exist_ok=True)
        build_local_lake(DATA_ROOT)
        print(f"Built local shared lake at {DATA_ROOT}")
    else:
        print(f"Using shared lake on S3: {DATA_ROOT}")

    print(f"\nFanning out 8 concurrent agents, each with its own embedded DuckDB...")
    results = fan_out(DATA_ROOT, n_agents=8)

    # All agents read the same read-only data -> identical results, no contention.
    identical = all(r == results[0] for r in results)
    print(f"All 8 agents returned identical results: {identical}")
    print("\nAgent 0 revenue_by_region:")
    for region, (n, rev) in results[0].items():
        print(f"  region {region}: {n:,} events, ${rev:,.0f}")

    pruned = Agent(99, DATA_ROOT).one_day("2024-01-03")
    print(f"\nPartition-pruned read (dt=2024-01-03): {pruned:,} rows "
          f"(only that partition scanned).")
    print("\nDone -- embedded-per-agent + shared Parquet, concurrent reads, no server.")


if __name__ == "__main__":
    main()
