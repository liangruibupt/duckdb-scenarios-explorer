#!/usr/bin/env python3
"""
Context layer — what the engine is asked (cost gate) and what comes back
(result handles), plus history compression across turns.

Pure/near-pure helpers over sqlglot + an injected DuckDB connection. See
specs/GOVERNANCE_SPEC.md for the contract the tests assert.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import sqlglot
from sqlglot import exp

DIALECT = "duckdb"

MAX_EXPANDED_PARTITIONS = 366
MAX_RESULT_ROWS = 200
COMPRESSION_THRESHOLD = 0.6
MIN_MESSAGES_FOR_STUB = 6


class CostError(Exception):
    """Raised when the cost gate refuses a statement."""


class HandleError(Exception):
    """Raised when a result handle is missing or not owned by the session."""


# --- cost gate ---------------------------------------------------------------

def cost_gate(sql: str, partitioned_tables: dict[str, str],
              max_partitions: int = MAX_EXPANDED_PARTITIONS) -> None:
    """Refuse a raw partitioned source lacking a predicate on its partition col.

    `partitioned_tables` maps table name -> partition column that MUST be
    constrained. Raises CostError; returns None when the statement is allowed.
    """
    tree = sqlglot.parse_one(sql, dialect=DIALECT)
    referenced = {t.name for t in tree.find_all(exp.Table)}
    # columns that appear in any WHERE/AND predicate as a comparison
    constrained = _constrained_columns(tree)
    for tbl, part_col in partitioned_tables.items():
        if tbl in referenced and part_col not in constrained:
            raise CostError(
                f"table '{tbl}' is partitioned on '{part_col}'; a predicate on "
                f"'{part_col}' is required before scanning")
    # bound an over-wide IN / range on a partition col
    _check_partition_span(tree, partitioned_tables, max_partitions)


def _constrained_columns(tree: exp.Expression) -> set[str]:
    cols: set[str] = set()
    for pred in tree.find_all(exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
                              exp.In, exp.Between, exp.Like):
        for c in pred.find_all(exp.Column):
            cols.add(c.name)
    return cols


def _check_partition_span(tree, partitioned_tables, max_partitions) -> None:
    part_cols = set(partitioned_tables.values())
    for in_expr in tree.find_all(exp.In):
        col = in_expr.this
        if isinstance(col, exp.Column) and col.name in part_cols:
            n = len(in_expr.expressions)
            if n > max_partitions:
                raise CostError(
                    f"predicate on '{col.name}' spans {n} partitions "
                    f"(max {max_partitions})")


# --- result handles ----------------------------------------------------------

@dataclass
class ResultStore:
    """Owner-bound session result handles backed by DuckDB temp tables."""
    con: object
    owner: str
    max_rows: int = MAX_RESULT_ROWS
    _n: int = 0
    _owned: set[str] = field(default_factory=set)

    def run(self, sql: str) -> dict:
        """Execute; if the result exceeds max_rows, materialize as _r_<n> and
        return a handle instead of a truncated head."""
        rel = self.con.sql(sql)
        cols = rel.columns
        # peek row count cheaply
        total = self.con.sql(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        if total <= self.max_rows:
            return {"columns": cols, "rows": rel.fetchall(), "row_count": total,
                    "handle": None}
        self._n += 1
        handle = f"_r_{self._n}"
        self.con.execute(f"CREATE TEMP TABLE {handle} AS {sql}")
        self._owned.add(handle)
        samples = self.con.sql(f"SELECT * FROM {handle} LIMIT 3").fetchall()
        return {"columns": cols, "row_count": total, "handle": handle,
                "samples": samples, "retrieval": f"SELECT * FROM {handle}"}

    def read_handle(self, handle: str, sql: str) -> list:
        """Read a handle THIS session minted. A foreign/unknown handle is refused
        before the engine."""
        named = set(re.findall(r"_r_\d+", sql)) | {handle}
        foreign = named - self._owned
        if foreign:
            raise HandleError(
                f"result handle(s) {sorted(foreign)} not owned by this session")
        return self.con.sql(sql).fetchall()


# --- history compression -----------------------------------------------------

@dataclass
class Message:
    role: str
    content: str
    tokens: int
    handle: str | None = None      # set if content is a materialized result blob


def compress_history(messages: list[Message], window_tokens: int,
                     threshold: float = COMPRESSION_THRESHOLD,
                     min_messages: int = MIN_MESSAGES_FOR_STUB) -> list[Message]:
    """Once usage exceeds threshold*window, replace OLD materialized-result blobs
    with a one-line pointer to their handle. Current turn (last msg) untouched;
    nothing else dropped."""
    used = sum(m.tokens for m in messages)
    if len(messages) < min_messages or used <= threshold * window_tokens:
        return messages
    out: list[Message] = []
    for i, m in enumerate(messages):
        is_current = i == len(messages) - 1
        if m.handle and not is_current and m.tokens > 20:
            out.append(Message(role=m.role,
                               content=f"[materialized result → {m.handle}; "
                                       f"read with SELECT * FROM {m.handle}]",
                               tokens=15, handle=m.handle))
        else:
            out.append(m)
    return out


if __name__ == "__main__":
    import duckdb
    con = duckdb.connect()
    print("# cost gate")
    try:
        cost_gate("SELECT * FROM trips", {"trips": "dt"})
    except CostError as e:
        print("REFUSED:", e)
    cost_gate("SELECT * FROM trips WHERE dt = '2024-01-01'", {"trips": "dt"})
    print("OK: predicate on dt accepted")

    print("\n# result handles")
    con.execute("CREATE TABLE big AS SELECT range AS i FROM range(1000)")
    store = ResultStore(con, owner="alice", max_rows=200)
    r = store.run("SELECT * FROM big")
    print("handle:", r["handle"], "row_count:", r["row_count"])
    print("read-back rows:", len(store.read_handle(r["handle"], r["retrieval"])))
    try:
        store.read_handle("_r_99", "SELECT * FROM _r_99")
    except HandleError as e:
        print("REFUSED foreign:", e)
