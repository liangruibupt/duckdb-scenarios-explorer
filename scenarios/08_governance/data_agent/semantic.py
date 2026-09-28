#!/usr/bin/env python3
"""
Semantic layer — registered KPIs compiled deterministically to governed SQL.

The model calls a metric by NAME with allow-listed dimensions/time range; it
cannot improvise the SQL. An unregistered metric or a dimension outside the
metric's allow-list is refused. The compiled SQL then runs through the SAME
govern -> cost -> execute pipeline, so RLS/CLS and the cost gate still apply.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from . import pipeline as pl


class SemanticError(Exception):
    """Unregistered metric, or a dimension/filter outside the allow-list."""


@dataclass(frozen=True)
class Metric:
    name: str
    table: str
    agg: str                                  # e.g. "count(*)" or "sum(total_amount)"
    dimensions: tuple[str, ...] = ()          # allow-listed group-by columns
    time_column: str | None = None            # allow-listed time predicate column
    default_filters: tuple[str, ...] = ()     # extra SQL boolean exprs, ANDed


class Registry:
    def __init__(self, metrics: list[Metric]):
        self._m = {m.name: m for m in metrics}

    def get(self, name: str) -> Metric:
        if name not in self._m:
            raise SemanticError(f"unregistered metric: {name!r}")
        return self._m[name]

    def compile(self, name: str, *, dimensions=(), time_range=None,
                filters=()) -> str:
        """Deterministically compile a metric call to one SELECT. Raises
        SemanticError for any dimension/time/filter outside the allow-list."""
        m = self.get(name)
        dims = tuple(dimensions)
        for d in dims:
            if d not in m.dimensions:
                raise SemanticError(
                    f"dimension {d!r} not allowed for metric {name!r} "
                    f"(allowed: {list(m.dimensions)})")
        select_cols = list(dims) + [f"{m.agg} AS {name}"]
        sql = f"SELECT {', '.join(select_cols)} FROM {m.table}"

        wheres = list(m.default_filters)
        if time_range is not None:
            if not m.time_column:
                raise SemanticError(f"metric {name!r} has no time column")
            lo, hi = time_range
            wheres.append(f"{m.time_column} >= '{lo}' AND {m.time_column} < '{hi}'")
        # extra filters must be simple `col = literal` on an allow-listed dimension
        for f in filters:
            col = f.split()[0]
            if col not in m.dimensions and col != m.time_column:
                raise SemanticError(f"filter column {col!r} not allow-listed")
            wheres.append(f)
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        if dims:
            sql += " GROUP BY " + ", ".join(dims)
        return sql


def call_metric(registry: Registry, name: str, tenant, role, *, policies,
                partitioned, store, dimensions=(), time_range=None, filters=()):
    """Compile the metric then run it through the governed pipeline."""
    sql = registry.compile(name, dimensions=dimensions, time_range=time_range,
                           filters=filters)
    return pl.run_statement(sql, tenant, role, policies=policies,
                            partitioned=partitioned, store=store)
