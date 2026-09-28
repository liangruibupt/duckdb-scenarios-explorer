#!/usr/bin/env python3
"""
Scenario 09 -- Iceberg-style table differentiators with DuckLake.

Raw Parquet on S3 is immutable and catalog-less. A table format (Iceberg /
DuckLake) adds ACID snapshots, time-travel, schema evolution and row-level
UPDATE/DELETE. This demo proves each, fully offline (DuckLake = a local
read/write Iceberg-style format: SQL catalog + Parquet data).

The cloud analogue is Amazon S3 Tables (Iceberg REST); DuckDB reads those via the
`iceberg` extension's `iceberg_scan` — see ICEBERG_SPEC.md.

  python tables.py     # builds a DuckLake table and demonstrates all four
"""
from __future__ import annotations
import os
import tempfile
import duckdb


def connect(tmp: str):
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    cat = os.path.join(tmp, "catalog.ducklake")
    data = os.path.join(tmp, "data")
    con.execute(f"ATTACH 'ducklake:{cat}' AS lake (DATA_PATH '{data}')")
    con.execute("USE lake")
    return con


def snapshots(con) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('lake') ORDER BY snapshot_id"
    ).fetchall()]


def demo(con) -> dict:
    con.execute("CREATE TABLE orders (id INT, region VARCHAR, amount INT)")
    con.execute("INSERT INTO orders VALUES (1,'us',100),(2,'eu',200),(3,'us',300)")
    v_initial = max(snapshots(con))                      # snapshot after first load

    # row-level UPDATE + DELETE (impossible on immutable Parquet)
    con.execute("UPDATE orders SET amount = 999 WHERE id = 2")
    con.execute("DELETE FROM orders WHERE id = 3")

    # schema evolution: add a column; old snapshots still read
    con.execute("ALTER TABLE orders ADD COLUMN priority VARCHAR")
    con.execute("INSERT INTO orders VALUES (4,'ap',400,'high')")

    current = con.execute("SELECT * FROM orders ORDER BY id").fetchall()
    as_of = con.execute(
        f"SELECT id, region, amount FROM orders AT (VERSION => {v_initial}) "
        f"ORDER BY id").fetchall()

    return {
        "snapshots": snapshots(con),
        "initial_version": v_initial,
        "current": current,          # id2 amount=999, id3 gone, id4 has priority
        "as_of_initial": as_of,      # id2 amount=200, id3 present, no priority col
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        con = connect(tmp)
        r = demo(con)
        print("Snapshots (commit history):", r["snapshots"])
        print(f"\n# Current table (after UPDATE id2, DELETE id3, ADD priority, +id4):")
        for row in r["current"]:
            print("  ", row)
        print(f"\n# Time-travel AS OF version {r['initial_version']} "
              f"(before the update/delete/evolution):")
        for row in r["as_of_initial"]:
            print("  ", row)
        print("\nRaw Parquet can do NONE of these: no snapshots, no time-travel, "
              "no in-place UPDATE/DELETE, no schema evolution without a rewrite.")


if __name__ == "__main__":
    main()
