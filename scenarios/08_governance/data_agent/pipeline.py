#!/usr/bin/env python3
"""
Statement pipeline — one path every statement takes:

    govern (RLS/CLS/allow-list/shape) -> cost gate -> execute + shape

The governed SQL, not the raw SQL, is what the cost gate and the engine see.
A refusal at any stage names the stage and the engine is never reached. Every
statement emits one audit record (the trace the sample streams to its UI).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re

from . import governance as gov
from . import context as ctx


@dataclass
class Audit:
    principal: str
    stage_reached: str
    ok: bool
    rls_applied: bool = False
    cls_excluded: bool = False
    rows: int | None = None
    handle: str | None = None
    error: str | None = None


def run_statement(sql: str, tenant: str | None, role: str | None, *,
                  policies: dict, partitioned: dict, store) -> dict:
    """Run one statement through the full pipeline. Returns
    {result, audit}; on refusal returns {refused: {stage, error}, audit}."""
    principal = f"{tenant}:{role}" if tenant and role else "anonymous"
    policy = gov.resolve_policy(policies, tenant, role)

    # 1) govern
    try:
        governed = gov.govern(sql, policy)
    except gov.GovernanceError as e:
        return _refuse(principal, "govern", str(e))

    rls = " AND " in governed.upper() or "WHERE" in governed.upper()
    cls = "EXCLUDE" in governed.upper()

    # 2) cost gate — on the GOVERNED sql
    try:
        ctx.cost_gate(governed, partitioned)
    except ctx.CostError as e:
        a = _audit(principal, "cost", False, rls, cls, error=str(e))
        return {"refused": {"stage": "cost", "error": str(e)}, "audit": a}

    # 3) execute + shape
    try:
        r = store.run(governed)
    except Exception as e:
        a = _audit(principal, "execute", False, rls, cls, error=str(e)[:200])
        return {"refused": {"stage": "execute", "error": str(e)[:200]}, "audit": a}

    a = _audit(principal, "execute", True, rls, cls,
               rows=r.get("row_count"), handle=r.get("handle"))
    return {"result": r, "governed_sql": governed, "audit": a}


def _refuse(principal, stage, msg):
    return {"refused": {"stage": stage, "error": msg},
            "audit": _audit(principal, stage, False, error=msg)}


def _audit(principal, stage, ok, rls=False, cls=False, rows=None, handle=None,
           error=None) -> Audit:
    return Audit(principal=principal, stage_reached=stage, ok=ok,
                 rls_applied=rls, cls_excluded=cls, rows=rows, handle=handle,
                 error=error)
