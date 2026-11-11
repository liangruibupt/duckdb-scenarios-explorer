#!/usr/bin/env python3
"""
Federation -- join lake tables with a non-lake source inside one governed session.

The article's L5 pattern: a non-lake source (reached through AgentCore Gateway
in the AWS sample) is called as a *registered tool*, not with free SQL. The
result is landed in the session's DuckDB as an owner-bound handle `_x_<n>`, and
the agent then joins it with governed lake tables in ordinary SQL.

Guarantees enforced here, before the engine:
  * Only registered tools can be called, and only by principals on the tool's
    allow-list.
  * The tenant is bound from the session principal, never from the model's
    arguments, so a tool can only return the caller's own tenant.
  * A statement may reference only `_x_` handles this session minted; a foreign
    handle is refused.
  * Everything else in the statement goes through scenario 08's `govern()`
    under the caller's (Lake Formation derived) policy, and through the cost gate.
"""
from __future__ import annotations

import itertools
import pathlib
import re
import sqlite3
import sys
from dataclasses import dataclass, field

import pyarrow as pa

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "08_governance"))
from data_agent import governance as gov  # noqa: E402
from data_agent import context as ctx  # noqa: E402

_HANDLE = re.compile(r"\b_x_\d+\b")
# Handle numbers are unique across sessions in a process, so one session's
# handle name can never collide with (or be mistaken for) another's.
_HANDLE_IDS = itertools.count(1)


class FederationError(Exception):
    """A tool call or a handle reference was refused."""


@dataclass(frozen=True)
class Tool:
    """A registered call into a non-lake source (one Gateway tool)."""
    name: str
    sql: str                         # parameterized; must use :tenant
    allowed_principals: frozenset[str]
    params: tuple[str, ...] = ()     # extra arguments the model may pass


@dataclass
class FederatedSession:
    con: object                      # the session's DuckDB connection
    tenant: str
    role: str
    policies: dict
    tools: dict[str, Tool]
    external: sqlite3.Connection     # stand-in for the non-lake system
    partitioned: dict = field(default_factory=dict)
    _n: int = 0
    _owned: set[str] = field(default_factory=set)
    audit: list[dict] = field(default_factory=list)

    @property
    def principal(self) -> str:
        return f"{self.tenant}:{self.role}"

    # -- external source --------------------------------------------------
    def call_tool(self, name: str, **args) -> str:
        """Run a registered tool and land its rows as handle `_x_<n>`."""
        tool = self.tools.get(name)
        if tool is None:
            raise FederationError(f"tool '{name}' is not registered")
        if self.principal not in tool.allowed_principals:
            raise FederationError(f"tool '{name}' not permitted for {self.principal}")
        extra = set(args) - set(tool.params)
        if extra:
            raise FederationError(f"tool '{name}' does not accept {sorted(extra)}")
        # declared params default to None; tenant always comes from the session
        bound = {**{p: None for p in tool.params}, **args, "tenant": self.tenant}
        cur = self.external.execute(tool.sql, bound)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        self._n += 1
        handle = f"_x_{next(_HANDLE_IDS)}"
        arrow = pa.table({c: [r[i] for r in rows] for i, c in enumerate(cols)})
        self.con.register("_x_landing", arrow)
        try:
            self.con.execute(f"CREATE TEMP TABLE {handle} AS SELECT * FROM _x_landing")
        finally:
            self.con.unregister("_x_landing")
        self._owned.add(handle)
        self.audit.append({"stage": "tool", "tool": name, "handle": handle,
                           "rows": len(rows), "principal": self.principal})
        return handle

    # -- governed SQL over lake + handles ---------------------------------
    def query(self, sql: str) -> dict:
        named = set(_HANDLE.findall(sql))
        foreign = named - self._owned
        if foreign:
            self.audit.append({"stage": "handles", "ok": False, "sql": sql})
            raise FederationError(f"handle(s) {sorted(foreign)} not owned by this session")
        base = gov.resolve_policy(self.policies, self.tenant, self.role)
        if base.unrestricted:
            policy = base
        else:
            # owned handles are allowed tables with no extra filter: their rows
            # were already scoped to the caller's tenant when the tool ran
            policy = gov.Policy(tables={**base.tables,
                                        **{h: gov.TablePolicy() for h in named}})
        try:
            governed = gov.govern(sql, policy)
            ctx.cost_gate(governed, self.partitioned)
        except (gov.GovernanceError, ctx.CostError) as e:
            self.audit.append({"stage": "govern", "ok": False, "error": str(e)})
            raise
        cur = self.con.execute(governed)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        self.audit.append({"stage": "execute", "ok": True, "rows": len(rows),
                           "principal": self.principal})
        return {"columns": cols, "rows": rows, "governed_sql": governed}
