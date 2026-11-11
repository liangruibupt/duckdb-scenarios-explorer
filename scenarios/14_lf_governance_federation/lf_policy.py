#!/usr/bin/env python3
"""
Lake Formation -> scenario 08 Policy.

Turns a Lake Formation permission snapshot into the `Policy` objects that
scenario 08's `govern()` rewriter already enforces, so the policy authority is
Lake Formation and the enforcement point stays "before the engine".

Input is a snapshot dict with the same shapes the read-only APIs return:

    {
      "permissions":  <lakeformation list-permissions  PrincipalResourcePermissions[]>,
      "cell_filters": <lakeformation list-data-cells-filter DataCellsFilters[]>,
      "tables":       {"<db>.<table>": ["col", ...]}   # from glue get-tables
    }

`fetch_lf.py` builds this snapshot from a live account; tests use a fixture.

Mapping rules (all fail-closed):
  * Only grants that include SELECT (or ALL) count. DESCRIBE alone grants nothing.
  * Table               -> every column, every row.
  * TableWildcard       -> every table in the database, every column, every row.
  * TableWithColumns    -> ColumnNames = allow-list; ColumnWildcard minus
                           ExcludedColumnNames = deny-list.
  * DataCellsFilter     -> RowFilter.FilterExpression becomes the row filter
                           (AllRowsWildcard = no row filter) plus the filter's
                           column allow/deny list.
  * Several grants for one principal and table are combined as a union, as Lake
    Formation does: allowed columns are unioned and row filters are ORed; any
    grant with no row filter means all rows.
  * A principal ARN not in `principal_map` gets nothing (deny-all floor).
  * A row filter sqlglot cannot parse, a filter that names an unknown table, or a
    table missing from `tables` drops that table from the policy instead of
    granting it unfiltered.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field

import sqlglot

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "08_governance"))
from data_agent.governance import Policy, TablePolicy  # noqa: E402

DIALECT = "duckdb"
_GRANTING = {"SELECT", "ALL"}


@dataclass
class _Grant:
    all_columns: bool = False
    allowed: set[str] = field(default_factory=set)
    all_rows: bool = False
    row_filters: list[str] = field(default_factory=list)
    broken: bool = False            # an unparseable/unknown filter -> drop table


def _grants_select(perm: dict) -> bool:
    return bool(_GRANTING & set(perm.get("Permissions", [])))


def _valid_filter(expr: str) -> bool:
    try:
        return sqlglot.parse_one(expr, dialect=DIALECT) is not None
    except Exception:
        return False


def _apply_columns(g: _Grant, cols: list[str], names: list[str] | None,
                   wildcard: dict | None) -> None:
    """Add a grant's column scope to `g` (union)."""
    if names:
        g.allowed |= {c.lower() for c in names}
    elif wildcard is not None:
        excluded = {c.lower() for c in wildcard.get("ExcludedColumnNames", [])}
        if excluded:
            g.allowed |= {c for c in cols if c not in excluded}
        else:
            g.all_columns = True
    else:
        g.all_columns = True


def policies_from_lf(snapshot: dict, principal_map: dict[str, str]) -> dict[str, Policy]:
    """Lake Formation snapshot -> {"tenant:role": Policy}."""
    tables = {k.lower(): [c.lower() for c in v]
              for k, v in snapshot.get("tables", {}).items()}
    filters = {(f["DatabaseName"].lower(), f["TableName"].lower(), f["Name"]): f
               for f in snapshot.get("cell_filters", [])}
    grants: dict[str, dict[str, _Grant]] = {}

    def grant(principal: str, key: str) -> _Grant | None:
        if key not in tables:
            return None
        return grants.setdefault(principal, {}).setdefault(key, _Grant())

    for perm in snapshot.get("permissions", []):
        arn = perm.get("Principal", {}).get("DataLakePrincipalIdentifier", "")
        principal = principal_map.get(arn)
        if principal is None or not _grants_select(perm):
            continue
        res = perm.get("Resource", {})
        if "Table" in res:
            t = res["Table"]
            db = t["DatabaseName"].lower()
            if "TableWildcard" in t:
                keys = [k for k in tables if k.split(".", 1)[0] == db]
            else:
                keys = [f"{db}.{t['Name'].lower()}"]
            for key in keys:
                g = grant(principal, key)
                if g:
                    g.all_columns = g.all_rows = True
        elif "TableWithColumns" in res:
            t = res["TableWithColumns"]
            key = f"{t['DatabaseName'].lower()}.{t['Name'].lower()}"
            g = grant(principal, key)
            if g:
                _apply_columns(g, tables[key], t.get("ColumnNames"),
                               t.get("ColumnWildcard"))
                g.all_rows = True
        elif "DataCellsFilter" in res:
            r = res["DataCellsFilter"]
            db, tbl = r["DatabaseName"].lower(), r["TableName"].lower()
            key = f"{db}.{tbl}"
            g = grant(principal, key)
            if g is None:
                continue
            f = filters.get((db, tbl, r["Name"]))
            if f is None:
                g.broken = True          # grant points at a filter we cannot see
                continue
            _apply_columns(g, tables[key], f.get("ColumnNames"),
                           f.get("ColumnWildcard"))
            rf = f.get("RowFilter", {})
            if "AllRowsWildcard" in rf:
                g.all_rows = True
            elif rf.get("FilterExpression") and _valid_filter(rf["FilterExpression"]):
                g.row_filters.append(rf["FilterExpression"])
            else:
                g.broken = True
        # any other resource type (Database, DataLocation, LF-Tag...) grants
        # no table data here

    out: dict[str, Policy] = {}
    for principal, per_table in grants.items():
        tps: dict[str, TablePolicy] = {}
        for key, g in per_table.items():
            if g.broken:
                continue
            if not g.all_rows and not g.row_filters:
                continue
            cols = tables[key]
            allowed = set(cols) if g.all_columns else g.allowed & set(cols)
            if not allowed:
                continue
            row_filter = None if g.all_rows else " OR ".join(
                f"({e})" for e in g.row_filters)
            deny = tuple(sorted(set(cols) - allowed))
            # scenario 08's govern() matches tables by bare name
            tps[key.split(".", 1)[1]] = TablePolicy(row_filter=row_filter,
                                                    deny_columns=deny)
        out[principal] = Policy(tables=tps)
    return out
