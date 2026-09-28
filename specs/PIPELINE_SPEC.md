# Pipeline + Semantic layer — spec

Builds on scenario 08. Wires the layers into ONE statement pipeline and adds the
semantic (registered-metric) layer. AI-DLC: this spec is what `tests/` asserts.

## Statement pipeline (`data_agent/pipeline.py`)

`run_statement(sql, principal, *, con, policies, partitioned, store)` runs the
stages in order and returns a result dict OR raises the stage's typed error:

1. **govern**  — `governance.govern(sql, policy)` (RLS/CLS/allow-list/shape).
2. **cost**    — `context.cost_gate(governed_sql, partitioned)`.
3. **execute + shape** — `store.run(governed_sql)` (inline or `_r_<n>` handle).

Invariants:
- The governed SQL (not the raw SQL) is what the cost gate and engine see —
  order is govern→cost→execute, never execute-then-check.
- A refusal at any stage names the stage (`{stage, error}`) and the engine is
  never reached.
- The pipeline emits one **audit record** per statement:
  `{principal, stage_reached, rls_applied, cls_excluded, rows, handle}` — the
  trace the sample streams to its UI.

## Semantic layer (`data_agent/semantic.py`)

Registered KPIs compiled deterministically to governed SQL — the model calls a
metric by name, it cannot improvise the SQL.

- A `Metric` = name, base table, an aggregate expr, allowed `dimensions`,
  allowed `time_column`, optional default filters.
- `call_metric(name, dimensions, time_range, filters, principal, ...)`:
  - an **unregistered metric** name → refused.
  - a **dimension not in the metric's allow-list** → refused (no injection).
  - compiles to a single `SELECT agg, dims FROM table WHERE <time+filters> GROUP
    BY dims`, then runs it **through the same govern→cost→execute pipeline**, so
    RLS/CLS and the cost gate still apply to a metric call.
- The compiled SQL is deterministic for the same inputs.

## Chat-BI wiring

`scenarios/04_chat_bi/chat_bi.py` gains an optional governed path
(`--principal tenant:role`): NL → `rule_plan` SQL → `run_statement(...)` so a
demo question runs the full govern→cost→execute→shape flow. Default (no
principal) keeps the existing ungoverned behaviour so the older tests/CI are
unaffected.

## Test tiers
All **offline** (sqlglot + in-memory DuckDB). Runs in the existing CI job.
