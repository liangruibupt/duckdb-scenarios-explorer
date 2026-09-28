#!/usr/bin/env python3
"""
Scenario 09 -- copy-on-write (CoW) vs merge-on-read (MoR), by observable signature.

Both express a row-level delete on immutable Parquet files; they differ in what
happens to the FILES:
  - CoW: rewrite the affected data file(s)         -> data file_count changes
  - MoR: append a small delete file, data untouched -> delete_file_count grows

DuckLake uses a merge-on-read style delete: `ducklake_table_info` exposes both
`file_count` and `delete_file_count`, so we can SHOW the MoR signature directly,
and contrast it with what a CoW rewrite would look like (a full rewrite of the
table into new data files with no delete file).

  python cow_vs_mor.py
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


def _sig(con, table):
    fc, dfc = con.execute(
        f"SELECT file_count, delete_file_count FROM ducklake_table_info('lake') "
        f"WHERE table_name='{table}'").fetchone()
    return {"data_files": fc, "delete_files": dfc}


def demo(con) -> dict:
    con.execute("CREATE TABLE t AS SELECT range id, (range%100) v FROM range(50000)")
    base = _sig(con, "t")

    # merge-on-read style delete (DuckLake default): append a delete file
    con.execute("DELETE FROM t WHERE v = 7")
    mor = _sig(con, "t")

    # copy-on-write equivalent: fully rewrite the surviving rows into fresh data
    # files (no delete file). This is what a CoW engine does on delete.
    con.execute("CREATE TABLE t_cow AS SELECT * FROM t")   # materialize survivors
    cow = _sig(con, "t_cow")

    return {"base": base, "mor_after_delete": mor, "cow_rewrite": cow,
            "rows_after": con.execute("SELECT count(*) FROM t").fetchone()[0]}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = demo(_lake(tmp))
    print("Row-level DELETE on immutable Parquet — two strategies, two signatures:\n")
    print(f"  base table              : {r['base']}")
    print(f"  after MoR delete (v=7)  : {r['mor_after_delete']}  "
          f"<- delete_files grows, data files NOT rewritten (cheap write)")
    print(f"  CoW-style rewrite       : {r['cow_rewrite']}  "
          f"<- fresh data files, NO delete file (cheap read, expensive write)")
    print(f"  rows after delete       : {r['rows_after']:,}\n")
    print("Choose CoW when reads dominate (no read-time overlay); choose MoR when "
          "writes/upserts are frequent (cheap deletes) + a compaction job keeps "
          "the delete overlay small. See docs/WHY_ICEBERG.md.")


if __name__ == "__main__":
    main()
