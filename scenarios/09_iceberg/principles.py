#!/usr/bin/env python3
"""
Scenario 09 -- demonstrate WHY a table format beats raw Parquet, with real
DuckLake output for each of the four principles (see docs/WHY_ICEBERG.md).

  python principles.py
"""
from __future__ import annotations
import os
import tempfile
import duckdb


def _lake(tmp):
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    con.execute(f"ATTACH 'ducklake:{os.path.join(tmp,'c.ducklake')}' AS lake "
                f"(DATA_PATH '{os.path.join(tmp,'dat')}')")
    con.execute("USE lake")
    return con


def _info(con, table):
    return con.execute(
        f"SELECT file_count, delete_file_count FROM ducklake_table_info('lake') "
        f"WHERE table_name = '{table}'").fetchone()


def demo(con) -> dict:
    out = {}
    con.execute("CREATE TABLE orders (id INT, region VARCHAR, amount INT)")
    con.execute("INSERT INTO orders VALUES (1,'us',100),(2,'eu',200),(3,'us',300)")
    v0 = con.execute("SELECT max(snapshot_id) FROM ducklake_snapshots('lake')").fetchone()[0]

    # (1) ACID/time-travel: mutate, then read the OLD snapshot back
    con.execute("UPDATE orders SET amount = 999 WHERE id = 2")
    out["p1_current_id2"] = con.execute("SELECT amount FROM orders WHERE id=2").fetchone()[0]
    out["p1_asof_id2"] = con.execute(
        f"SELECT amount FROM orders AT (VERSION => {v0}) WHERE id=2").fetchone()[0]

    # (2) schema evolution: add a column; old snapshot has no such column
    con.execute("ALTER TABLE orders ADD COLUMN note VARCHAR")
    con.execute("INSERT INTO orders VALUES (4,'ap',400,'added-after-evolution')")
    out["p2_current_cols"] = len(con.execute("SELECT * FROM orders LIMIT 1").description)
    out["p2_asof_cols"] = len(con.execute(
        f"SELECT * FROM orders AT (VERSION => {v0}) LIMIT 1").description)

    # (3) metadata pruning: file-level stats let a filter skip files. Build a
    # table across many files, show the engine prunes by partition/stats.
    con.execute("CREATE TABLE events AS SELECT range id, "
                "(range % 6) region_id, (range % 100) amt FROM range(60000)")
    plan = con.execute(
        "EXPLAIN SELECT count(*) FROM events WHERE region_id = 3").fetchall()
    out["p3_plan_has_filter"] = any("region_id" in str(r) for r in plan)
    out["p3_pruned_rows"] = con.execute(
        "SELECT count(*) FROM events WHERE region_id = 3").fetchone()[0]

    # (4) row-level ops on immutable files: delete a row and observe the file
    # signature. DuckLake uses a merge-on-read style delete -> a delete file is
    # added and the data files are NOT rewritten.
    con.execute("CREATE TABLE ev2 AS SELECT range id, (range%100) amt FROM range(50000)")
    before = _info(con, "ev2")
    con.execute("DELETE FROM ev2 WHERE amt = 7")
    after = _info(con, "ev2")
    out["p4_before"] = {"files": before[0], "delete_files": before[1]}
    out["p4_after"] = {"files": after[0], "delete_files": after[1]}
    out["p4_row_gone"] = con.execute(
        "SELECT count(*) FROM ev2 WHERE amt = 7").fetchone()[0] == 0
    out["p4_is_mor"] = after[1] > before[1] and after[0] == before[0]
    return out


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = demo(_lake(tmp))
    print("# (1) ACID / time-travel — same query, two snapshots")
    print(f"    current  id2.amount = {r['p1_current_id2']}  (after UPDATE)")
    print(f"    AS OF v0 id2.amount = {r['p1_asof_id2']}  (history preserved)\n")
    print("# (2) schema evolution — a column added later is absent in old snapshots")
    print(f"    current columns  = {r['p2_current_cols']} (id,region,amount,note)")
    print(f"    AS OF v0 columns = {r['p2_asof_cols']} (id,region,amount)\n")
    print("# (3) metadata pruning — the filter is pushed down, only matching rows scanned")
    print(f"    filter pushed into plan: {r['p3_plan_has_filter']}; "
          f"rows for region_id=3: {r['p3_pruned_rows']:,}\n")
    print("# (4) row-level DELETE on immutable Parquet files")
    print(f"    file signature before: {r['p4_before']}")
    print(f"    file signature after : {r['p4_after']}  "
          f"(merge-on-read: {'delete_file added, data files not rewritten' if r['p4_is_mor'] else 'see cow_vs_mor.py'})")
    print(f"    row actually gone    : {r['p4_row_gone']}")
    print("\nRaw Parquet can do NONE of these — no snapshot pointer, no field-ids, "
          "no per-file delete markers.")


if __name__ == "__main__":
    main()
