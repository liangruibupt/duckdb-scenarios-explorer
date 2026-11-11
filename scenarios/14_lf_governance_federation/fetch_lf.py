#!/usr/bin/env python3
"""
Build a Lake Formation snapshot from a live account (read-only).

Calls only list/get APIs:
  lakeformation:ListPermissions, lakeformation:ListDataCellsFilter,
  glue:GetTables
and writes the JSON shape `lf_policy.policies_from_lf()` reads. Nothing in the
account is changed.

Usage:
  python fetch_lf.py --database sales --principal-map map.json --out lf_snapshot.json
  # map.json: {"arn:aws:iam::<acct>:role/acme-analyst": "acme:analyst", ...}

The caller needs Lake Formation data-lake-admin or equivalent read access to
list other principals' permissions.
"""
from __future__ import annotations

import argparse
import json


def _paged(call, key, **kw):
    token = None
    while True:
        resp = call(**kw, **({"NextToken": token} if token else {}))
        yield from resp.get(key, [])
        token = resp.get("NextToken")
        if not token:
            return


def fetch(database: str, region: str | None = None, catalog_id: str | None = None) -> dict:
    import boto3
    lf = boto3.client("lakeformation", region_name=region)
    glue = boto3.client("glue", region_name=region)
    cat = {"CatalogId": catalog_id} if catalog_id else {}

    tables = {}
    for t in _paged(glue.get_tables, "TableList", DatabaseName=database, **cat):
        cols = [c["Name"] for c in t.get("StorageDescriptor", {}).get("Columns", [])]
        cols += [c["Name"] for c in t.get("PartitionKeys", [])]
        tables[f"{database}.{t['Name']}"] = cols

    perms, skipped = [], []
    for name in [k.split(".", 1)[1] for k in tables]:
        res = {"Table": {"DatabaseName": database, "Name": name, **cat}}
        try:
            perms += list(_paged(lf.list_permissions, "PrincipalResourcePermissions",
                                 Resource=res, IncludeRelated="TRUE"))
        except lf.exceptions.InvalidInputException as e:
            # e.g. a resource-link database: list grants on the target catalog
            skipped.append(f"{database}.{name}: {e}")
    filters = list(_paged(lf.list_data_cells_filter, "DataCellsFilters"))
    filters = [f for f in filters if f["DatabaseName"] == database]
    return {"tables": tables, "permissions": perms, "cell_filters": filters,
            "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database", required=True)
    ap.add_argument("--principal-map", required=True,
                    help="JSON file mapping principal ARN -> 'tenant:role'")
    ap.add_argument("--region")
    ap.add_argument("--catalog-id")
    ap.add_argument("--out", default="lf_snapshot.json")
    a = ap.parse_args()
    snap = fetch(a.database, a.region, a.catalog_id)
    with open(a.principal_map) as f:
        snap["principal_map"] = json.load(f)
    with open(a.out, "w") as f:
        json.dump(snap, f, indent=2, default=str)
    print(f"wrote {a.out}: {len(snap['tables'])} tables, "
          f"{len(snap['permissions'])} grants, {len(snap['cell_filters'])} cell filters")
    for s in snap["skipped"]:
        print(f"  skipped (tables get no policy, fail-closed): {s}")


if __name__ == "__main__":
    main()
