# Governance + Context layers — spec

Inspired by `aws-samples/sample-data-agent-on-duckdb`. This adds the two layers
that turn a naive NL→SQL tool into a *governed* data agent, wired into scenario
04's chat-BI pipeline. AI-DLC: this spec is the contract `tests/` asserts.

Pipeline order per statement: **govern → cost → execute → shape**, with history
compression across turns. Each stage is pure and independently testable.

---

## Governance layer — who may see what (`data_agent/governance.py`)

Identity-aware RLS/CLS **rewrite before the engine**, from a principal's policy,
using sqlglot. Fail-closed.

Invariants:
- **Deny-all floor**: an unknown/missing principal → role `deny-all`; every table
  reference is refused (no policy is NOT "allow").
- **RLS**: a role's `row_filter` for a table is ANDed into the WHERE of every
  reference to that table (base table, in a JOIN, in a subquery/CTE body).
- **CLS**: a role's `deny_columns` are `EXCLUDE`d from `SELECT *`; an *explicit*
  reference to a denied column is a **clean rejection** naming the column + role
  (not silently dropped).
- **Table allow-list**: a restricted role may reference only tables its policy
  names (plus statement-local CTE/subquery aliases). An unlisted table is refused
  before the engine.
- **Statement-shape allow-list**: only `SELECT` (incl. CTE/`UNION`/derived-table)
  passes. `INSERT/UPDATE/DELETE/COPY/ATTACH/CREATE/DROP` are refused for every
  role — including DML hidden behind a `WITH` prefix.
- **CTE cannot shadow a governed table**: `WITH trips AS (…)` does not unguard the
  real `trips`.
- **Host-reaching refused**: non-`s3://`/local paths and `read_text`/`read_csv`
  on local paths are refused for every role.
- **Totality**: unrestricted role passes unchanged; every other outcome is
  derived from the policy, asserted as a persona × table × shape matrix.

## Context layer (`data_agent/context.py`)

### Cost gate
- A raw partitioned source **without a partition predicate** is refused before
  execution (naming the missing column).
- A literal partition predicate is accepted; composes with the RLS WHERE (RLS
  ANDed in does not remove the user's partition filter).
- Knob: `MAX_EXPANDED_PARTITIONS` (default 366) — a predicate spanning more than
  this is refused.

### Result handles
- A result over `MAX_RESULT_ROWS` (default 200) is materialized as a session temp
  table `_r_<n>`; the caller gets `{rows, columns, samples(≤3), handle}` — never
  a truncated head presented as complete.
- A handle is **owner-bound**: reading `_r_<k>` the session did not mint is
  refused before the engine.

### History compression
- Given a transcript and a model-window budget, once usage exceeds
  `COMPRESSION_THRESHOLD` (default 0.6) of the window, old materialized-result
  blobs are replaced by a one-line pointer to their `_r_<n>`; the current turn is
  never touched; nothing else is dropped.
- Knob: `MIN_MESSAGES_FOR_STUB` (default 6) — below this, no compression.

## Test tiers
All **offline** (sqlglot rewrite + in-memory DuckDB temp tables); no network,
no S3, no tokens. Runs in the existing CI job.
