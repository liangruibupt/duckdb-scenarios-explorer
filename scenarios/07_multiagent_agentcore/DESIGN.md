# Scenario 07 — Multi-agent OLAP on AgentCore (design)

This scenario is a **design decision**, not a runnable script, so it follows the
same inspect → plan → implement → test loop as the code scenarios, with
"implement" = the recommended architecture and "test" = the validation criteria
you'd use to prove it in a real deployment.

---

## 1. Inspect — the problem & constraints

**Goal:** many agents (on Amazon Bedrock AgentCore Runtime) need to run ad-hoc
analytical (OLAP) queries over a shared dataset, cheaply and fast.

**Key facts that constrain the design:**
- DuckDB is an **embedded library**, not a server. There is no "DuckDB cluster"
  to point clients at — it runs *in the process* that imports it.
- DuckDB is **single-writer / multi-reader** on a given database file. Concurrent
  writers to one file corrupt or block.
- AgentCore Runtime instances are **ephemeral and horizontally scaled** — agent
  count varies with load; each has its own container filesystem and memory.
- The data is **read-heavy** for analytics; writes (if any) are a separate path.
- Cost sensitivity: we want **zero idle cost** and spend proportional to use.

**Anti-goal:** standing up a shared long-lived query service just to host DuckDB.

## 2. Plan — options considered

| Option | Where DuckDB runs | Verdict |
|--------|-------------------|---------|
| **A. Embedded per-agent** | a library inside each AgentCore Runtime, reading Parquet on S3 via `httpfs` | ✅ **recommended** |
| B. Shared DuckDB service | one long-lived box/container all agents query | ❌ reintroduces a server, idle cost, single-writer bottleneck, scaling ceiling |
| C. Managed query engine (Athena) | serverless, per-query | ⚠️ valid when data outgrows single-node or you want zero client libs; higher per-query latency/cost for hot small data |
| D. Warehouse (Redshift) | provisioned MPP | ❌ overkill for ad-hoc agent queries; idle capacity cost |

## 3. Implement — recommended architecture

**DuckDB embedded per-agent + Parquet-on-S3 as the shared read layer.**

```
                       ┌─────────────────────────┐
   AgentCore Runtime   │  agent process          │
   (scaled 1..N)       │   └─ DuckDB (in-proc)    │──httpfs──┐
                       └─────────────────────────┘          │
                       ┌─────────────────────────┐          ▼
                       │  agent process          │     ┌──────────────┐
                       │   └─ DuckDB (in-proc)    │──── │  S3: Parquet │
                       └─────────────────────────┘     │  hive-parted │
                             ... N agents ...           └──────────────┘
                                                          ▲ (writes:
                                                          │  separate path)
                                              OLTP (Aurora) or append-only
                                              immutable Parquet writer
```

**Decisions & rationale:**
- **Bundle DuckDB in the agent image / Lambda layer.** It's a single wheel; the
  engine scales exactly with the number of agents and costs nothing when idle.
- **S3 holds the data, not a DuckDB file.** Every agent reads shared, durable,
  concurrently-readable **Parquet on S3** through `httpfs` — this is scenario 02's
  pattern. Read-only Parquet has no writer-contention problem.
- **Hive-partition the Parquet** (`year=/month=/…`) so agents scan only the
  partitions a query needs (scenario 02 proves the pruning).
- **Never share one writable DuckDB file across agents.** Route writes to a real
  OLTP store (Aurora — the pattern from the cod-agent project) or have a *single*
  writer append immutable Parquet files that readers then pick up.
- **Per-agent limits:** set `SET memory_limit`/`threads` per container; reuse a
  warm connection within an invocation; optionally cache hot partitions on the
  runtime's ephemeral disk.

**Cost/perf summary:** cheapest (no idle infra), scales with agents, fast for
read-heavy ad-hoc OLAP. Add **Athena** only when the working set outgrows a
single node; add a **semantic layer** (Cube/dbt metrics) only when you need
governed metrics + multi-user caching — don't stack redundant engines.

## 4. Test — how you'd validate it in a real deployment

Acceptance criteria to prove the design holds (not asserted in this repo's
offline CI, since they need a live AgentCore + S3 environment):

- **Concurrency:** N agents issue reads against the same S3 Parquet
  simultaneously with no contention, no lock errors, and linear-ish aggregate
  throughput as N grows.
- **Idle cost = 0:** with no agents running, the only standing cost is S3
  storage — no query-engine compute billed.
- **Partition pruning:** a query filtered to one `year=/month=` scans only that
  partition's bytes (verify via S3 request/byte metrics), matching scenario 02.
- **Write isolation:** concurrent writes never touch a shared DuckDB file; the
  write path is OLTP or single-writer append-Parquet, and readers see new files
  without coordination.
- **Cold-start budget:** DuckDB import + first S3 query completes within the
  agent's latency budget; a warm connection reused within an invocation.

## Related scenarios
- **02 httpfs/S3** — the exact in-place S3 read + pruning this design relies on.
- **03 CSV→Parquet ETL** — how data lands as partitioned Parquet (Lambda/Fargate).
- **04 chat BI** — an agent that turns NL into DuckDB SQL over this shared layer.
