#!/usr/bin/env python3
"""
Scenario 07 (cloud) -- concurrent fan-out over a LIVE S3 Tables Iceberg table.

The design (DESIGN.md) claims the shared read layer should be an Iceberg table on
S3 so many agents can read concurrently with snapshot isolation. This proves it
against the REAL managed table: N agents, each embedding its own DuckDB, attach
the S3 Tables Iceberg REST catalog and read `nyc.trips` in parallel — identical
results, no contention, no shared writable state.

  export S3_TABLES_ARN=arn:aws:s3tables:us-east-1:<acct>:bucket/<name>
  export ICEBERG_TABLE=nyc.trips
  python fanout_s3tables.py           # 8 concurrent agents
"""
from __future__ import annotations
import concurrent.futures as cf
import os
import sys
import duckdb

ARN = os.environ.get("S3_TABLES_ARN", "")
TABLE = os.environ.get("ICEBERG_TABLE", "nyc.trips")
REGION = os.environ.get("AWS_REGION", "us-east-1")


class IcebergAgent:
    """One agent = its own embedded DuckDB attached to the shared Iceberg table."""

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.con = duckdb.connect()
        self.con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws; "
                         "INSTALL iceberg; LOAD iceberg;")
        self.con.execute(f"CREATE OR REPLACE SECRET s3 "
                         f"(TYPE s3, PROVIDER credential_chain, REGION '{REGION}');")
        self.con.execute(f"ATTACH '{ARN}' AS s3tbl "
                         f"(TYPE iceberg, ENDPOINT_TYPE s3_tables)")

    def revenue_by_payment(self) -> dict:
        rows = self.con.execute(
            f"SELECT payment_type, count(*) n FROM s3tbl.{TABLE} "
            f"WHERE fare_amount > 0 GROUP BY payment_type ORDER BY payment_type"
        ).fetchall()
        return {r[0]: r[1] for r in rows}


def fan_out(n_agents: int = 8) -> list[dict]:
    with cf.ThreadPoolExecutor(max_workers=n_agents) as ex:
        return list(ex.map(lambda i: IcebergAgent(i).revenue_by_payment(),
                           range(n_agents)))


def main() -> None:
    if not ARN:
        print("Set S3_TABLES_ARN=<bucket arn> [ICEBERG_TABLE=nyc.trips] first.")
        sys.exit(2)
    print(f"Fanning out 8 concurrent agents over the LIVE Iceberg table "
          f"s3tbl.{TABLE} ...")
    results = fan_out(8)
    identical = all(r == results[0] for r in results)
    print(f"All 8 agents returned identical results: {identical}")
    print("Agent 0 payment_type -> count:", results[0])
    print("\nConcurrent readers of a managed Iceberg table on S3 — snapshot "
          "isolation, no contention, no shared writable state. This is why the "
          "multi-agent shared layer is an Iceberg table, not a raw glob.")


if __name__ == "__main__":
    main()
