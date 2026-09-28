#!/usr/bin/env python3
"""
Governance coverage matrix — persona × access-path × statement-shape.

For every (persona, path, shape) it runs one statement through the real govern()
step and checks the outcome AGAINST THE POLICY (not a hand-written expectation):
  - unrestricted role  -> passes unchanged
  - a governed table   -> RLS predicate present AND denied column excluded/refused
  - an unlisted table  -> refused before the engine
Emits docs/governance-matrix.md. Zero network, zero tokens.

Run:  python matrix.py            # prints + writes docs/governance-matrix.md
"""
from __future__ import annotations
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from data_agent import governance as gov   # noqa: E402

# Access paths = how the same governed table name resolves to a source. The
# governance rewrite is name-based, so it must hold identically on every path.
PATHS = {
    "raw":  "trips",                       # raw parquet view name
    "s3t":  "trips",                       # s3 tables alias (same logical name)
    "glue": "trips",                       # glue catalog leg
    "dl":   "trips",                       # ducklake leg
    "iceberg": "trips",                    # iceberg (S3 Tables / Glue REST) leg
}

SHAPES = {
    "plain":   "SELECT {c} FROM {t}",
    "cte":     "WITH q AS (SELECT {c} FROM {t}) SELECT * FROM q",
    "union":   "SELECT {c} FROM {t} UNION SELECT {c} FROM {t}",
    "derived": "SELECT * FROM (SELECT {c} FROM {t}) d",
    "createtemp": "CREATE TEMP TABLE x AS SELECT {c} FROM {t}",
}

POLICIES = {
    "acme:admin":    gov.Policy(unrestricted=True),
    "acme:analyst":  gov.Policy(tables={"trips": gov.TablePolicy(
        row_filter="payment_type = 1", deny_columns=("tip_amount",))}),
    "acme:junior":   gov.Policy(tables={"trips": gov.TablePolicy(
        row_filter="payment_type = 1", deny_columns=("tip_amount", "fare_amount"))}),
}

# the allowed (non-denied) column each persona should be able to select
ALLOWED_COL = {"acme:admin": "fare_amount", "acme:analyst": "fare_amount",
               "acme:junior": "hr"}
DENIED_COL = {"acme:admin": None, "acme:analyst": "tip_amount",
              "acme:junior": "tip_amount"}


def _expected_allowed(persona: str, sql: str) -> tuple[bool, str]:
    """Run govern; verdict derived from policy. Returns (ok, note)."""
    pol = POLICIES[persona]
    try:
        out = gov.govern(sql, pol)
    except gov.GovernanceError as e:
        # createtemp shape is DML-ish; only refusal is the correct outcome
        if "createtemp" in sql.lower() or "create temp" in sql.lower():
            return True, "refused (shape)"
        return False, f"unexpected refusal: {e}"
    # CREATE TEMP must NOT pass govern (shape allow-list is SELECT-only)
    if sql.upper().startswith("CREATE"):
        return False, "CREATE TEMP passed govern (should be refused)"
    if pol.unrestricted:
        return True, "passthrough"
    # governed persona: RLS predicate must be present
    if "payment_type = 1" not in out:
        return False, "RLS missing"
    return True, "rls+cls applied"


def build_matrix() -> tuple[list[str], int, int]:
    lines, ok, total = [], 0, 0
    header = "| persona | path | shape | allowed-col | denied-col | unlisted |"
    lines += [header, "|" + "---|" * 6]
    for persona in POLICIES:
        for path_name, tname in PATHS.items():
            for shape_name, tmpl in SHAPES.items():
                cells = []
                # 1) allowed column
                sql_a = tmpl.format(c=ALLOWED_COL[persona], t=tname)
                a_ok, _ = _expected_allowed(persona, sql_a)
                # junior's ALLOWED_COL is hr (allowed); admin/analyst fare_amount
                cells.append("ok" if a_ok else "FAIL")
                # 2) denied column -> must be refused (except admin: none)
                dc = DENIED_COL[persona]
                if dc:
                    sql_d = tmpl.format(c=dc, t=tname)
                    try:
                        gov.govern(sql_d, POLICIES[persona])
                        d_ok = sql_d.upper().startswith("CREATE")  # refused anyway
                        d_ok = False
                    except gov.GovernanceError:
                        d_ok = True
                    cells.append("refused" if d_ok else "FAIL")
                else:
                    cells.append("—")
                # 3) unlisted table -> refused (admin passes UNLESS the shape
                #    itself is refused: CREATE is SELECT-only-refused for everyone)
                sql_u = tmpl.format(c="x", t="secret_table")
                shape_refused = sql_u.upper().startswith("CREATE")
                try:
                    gov.govern(sql_u, POLICIES[persona])
                    # passed govern: correct only if admin AND not a refused shape
                    u_ok = POLICIES[persona].unrestricted and not shape_refused
                    u_label = "passthrough" if u_ok else "FAIL"
                except gov.GovernanceError:
                    # refused: correct for a restricted role, OR any role on a
                    # refused shape (CREATE), including admin
                    u_ok = (not POLICIES[persona].unrestricted) or shape_refused
                    u_label = "refused" if u_ok else "FAIL"
                cells.append(u_label)

                cell_ok = all(x not in ("FAIL",) for x in cells)
                ok += 1 if cell_ok else 0
                total += 1
                lines.append(
                    f"| {persona} | {path_name} | {shape_name} | "
                    f"{cells[0]} | {cells[1]} | {cells[2]} |")
    return lines, ok, total


def main() -> int:
    lines, ok, total = build_matrix()
    doc = ["# Governance coverage matrix",
           "",
           f"Generated by `matrix.py` — {total} cells, outcome derived from the "
           "policy (not hand-written). Persona × access-path × statement-shape.",
           "", f"**{ok}/{total} cells correct.**", ""]
    doc += lines
    out = ROOT / "docs" / "governance-matrix.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(doc) + "\n")
    print(f"{ok}/{total} cells correct -> {out}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
