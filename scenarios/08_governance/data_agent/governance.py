#!/usr/bin/env python3
"""
Governance layer — identity-aware RLS/CLS rewrite BEFORE the engine.

Given a caller's {tenant, role} and a policy set, rewrite a SQL statement so the
engine only ever sees rows/columns the caller may see. Fail-closed: an unknown
principal, an unlisted table, a non-SELECT shape, a denied column named
explicitly, a CTE shadowing a governed table, or a host-reaching path are all
refused BEFORE the SQL reaches DuckDB.

Pure functions over sqlglot ASTs — no engine, no network. See
specs/GOVERNANCE_SPEC.md for the contract the tests assert.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import sqlglot
from sqlglot import exp

DIALECT = "duckdb"


class GovernanceError(Exception):
    """Raised when a statement is refused. Message names column/role/table."""


@dataclass(frozen=True)
class TablePolicy:
    row_filter: str | None = None          # SQL boolean expr, ANDed into WHERE
    deny_columns: tuple[str, ...] = ()      # columns EXCLUDEd / refused if named


@dataclass(frozen=True)
class Policy:
    """Per (tenant:role) policy: which tables, and each table's RLS/CLS."""
    tables: dict[str, TablePolicy] = field(default_factory=dict)
    unrestricted: bool = False              # admin: no rewrite, all tables

    def table_names(self) -> set[str]:
        return set(self.tables)


DENY_ALL = Policy(tables={}, unrestricted=False)   # the fail-closed floor

# statement roots that are allowed at all (SELECT-family only)
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Subquery)
_HOST_FUNCS = {"read_text", "read_blob"}            # local-reaching readers


def resolve_policy(policies: dict[str, Policy], tenant: str | None,
                   role: str | None) -> Policy:
    """principal -> policy. Missing/unknown => deny-all (never admin)."""
    if not tenant or not role:
        return DENY_ALL
    return policies.get(f"{tenant}:{role}", DENY_ALL)


def _table_name(t: exp.Table) -> str:
    return t.name


def _local_names(tree: exp.Expression) -> set[str]:
    """CTE names + derived-table aliases — statement-local, not governed tables."""
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        names.add(cte.alias_or_name)
    return names


def govern(sql: str, policy: Policy) -> str:
    """Rewrite `sql` under `policy`, or raise GovernanceError. Returns SQL."""
    try:
        tree = sqlglot.parse_one(sql, dialect=DIALECT)
    except Exception as e:
        raise GovernanceError(f"unparseable SQL: {e}")

    if tree is None:
        raise GovernanceError("empty statement")

    # 1) statement-shape allow-list (also catches DML behind a CTE prefix:
    #    the root of `WITH x AS (...) DELETE ...` is a Delete, not a Select)
    if not isinstance(tree, _ALLOWED_ROOTS):
        raise GovernanceError(
            f"statement type {type(tree).__name__} refused; only SELECT is allowed")
    for bad in tree.find_all(exp.Insert, exp.Update, exp.Delete, exp.Command,
                             exp.Create, exp.Drop):
        raise GovernanceError(f"non-SELECT operation refused: {type(bad).__name__}")

    # 2) host-reaching refusal (any role, incl. admin)
    for fn in tree.find_all(exp.Anonymous):
        if fn.name and fn.name.lower() in _HOST_FUNCS:
            raise GovernanceError(f"host-reaching function refused: {fn.name}")
    for lit in tree.find_all(exp.Literal):
        if lit.is_string:
            v = lit.this
            if (v.startswith("/") or v.startswith("http://")
                    or v.startswith("https://") or v.startswith("file:")):
                raise GovernanceError(f"non-s3 path refused: {v[:60]}")

    if policy.unrestricted:
        return tree.sql(dialect=DIALECT)   # admin: shape+host checked, no rewrite

    local = _local_names(tree)

    # 3) table allow-list + CTE-cannot-shadow-a-governed-table
    for cte in tree.find_all(exp.CTE):
        if cte.alias_or_name in policy.tables:
            raise GovernanceError(
                f"local name '{cte.alias_or_name}' may not shadow governed table")
    for tbl in tree.find_all(exp.Table):
        name = _table_name(tbl)
        if name in local:
            continue
        if name not in policy.tables:
            raise GovernanceError(
                f"table '{name}' not permitted for this role")

    # 4) CLS: refuse an explicitly-named denied column; EXCLUDE from SELECT *
    denied_by_table = {t: set(p.deny_columns) for t, p in policy.tables.items()}
    all_denied = set().union(*denied_by_table.values()) if denied_by_table else set()
    for col in tree.find_all(exp.Column):
        if col.name in all_denied:
            raise GovernanceError(
                f"column '{col.name}' denied for this role")
    # add EXCLUDE(denied...) onto SELECT * so `SELECT *` cannot leak them
    if all_denied:
        for star in tree.find_all(exp.Star):
            parent = star.parent
            if isinstance(parent, exp.Select):
                cols = ", ".join(sorted(all_denied))
                star.replace(sqlglot.parse_one(f"* EXCLUDE ({cols})", dialect=DIALECT))

    # 5) RLS: AND each table's row_filter into the query's WHERE
    for tbl in tree.find_all(exp.Table):
        name = _table_name(tbl)
        if name in local:
            continue
        rf = policy.tables[name].row_filter
        if not rf:
            continue
        select = tbl.find_ancestor(exp.Select)
        if select is None:
            continue
        pred = sqlglot.parse_one(rf, dialect=DIALECT)
        where = select.args.get("where")
        if where:
            select.set("where", exp.Where(
                this=exp.And(this=where.this, expression=pred)))
        else:
            select.set("where", exp.Where(this=pred))

    return tree.sql(dialect=DIALECT)


if __name__ == "__main__":
    # tiny demo
    pol = Policy(tables={
        "trips": TablePolicy(row_filter="payment_type = 1",
                             deny_columns=("tip_amount",)),
    })
    for q in ["SELECT * FROM trips",
              "SELECT fare_amount FROM trips WHERE trip_distance > 2",
              "SELECT tip_amount FROM trips",
              "SELECT * FROM secret_table",
              "WITH x AS (SELECT 1) DELETE FROM trips"]:
        try:
            print(f"IN : {q}\nOUT: {govern(q, pol)}\n")
        except GovernanceError as e:
            print(f"IN : {q}\nREFUSED: {e}\n")
