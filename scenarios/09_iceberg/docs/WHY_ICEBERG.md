# Why Iceberg can do what raw Parquet cannot

One sentence: **Parquet defines how data is stored *inside one file*; Iceberg
defines *which files — and which rows — make up a table at a given version*.**
The Parquet files underneath stay immutable; Iceberg adds indirection
(versioned metadata), statistics, and an atomic commit protocol on top. Every
capability below falls out of that one design.

## The two things being compared

- **Parquet (raw files + glob).** The data is a pile of `.parquet` files on S3.
  The "table" is whatever `read_parquet('s3://…/**/*.parquet')` lists **at query
  time**. Nothing records "which files make up this table right now."
- **Iceberg.** Same Parquet data files, plus a **metadata tree**:
  - `metadata.json` — the table's current state, pointing at the current snapshot.
  - `manifest list` → `manifest` — each snapshot **explicitly lists** its data
    files, and for each file its **statistics** (column min/max, row count,
    partition values).
  - A write = new data files + new manifest + **atomically swap** `metadata.json`
    to the new snapshot.

Raw Parquet infers "table = these files" by globbing on the spot; Iceberg
**records** it as swappable, stat-carrying metadata.

---

## Why, capability by capability

### 1. ACID commits & snapshots → time-travel, safe concurrent writes
The last step of a write is just **flipping one pointer** (`metadata.json` → new
snapshot), and that flip is **atomic**.
- A reader sees either the old snapshot or the new one, never a half-written
  state → **ACID isolation**.
- The old snapshot's manifest is **not deleted** → you can `AS OF <snapshot>`
  read history → **time-travel**.
- Two writers can proceed concurrently: each builds new files off the same base
  snapshot and commits via **optimistic concurrency** (compare-and-swap on the
  pointer); the loser retries → **safe concurrent writes**.

**Raw Parquet can't:** "table = glob result" is computed dynamically. While you
write new files, another reader's glob **sees the half-written files** — no
commit point, no atomic swap, no retained old version.

### 2. Schema & partition evolution → change columns/partitioning, no rewrite
Every Iceberg field has a **permanent field-id** (not name- or position-based),
and the schema lives in metadata, not in the files' physical layout.
- Add/rename a column, or change the partition spec = **metadata-only**; old data
  files are untouched and read back by field-id (missing columns return NULL).
- Partition evolution: new data uses the new spec, old data keeps the old spec;
  the engine knows from metadata which files use which.

**Raw Parquet can't:** partitioning is **encoded in the directory path**
(`year=2024/month=01/`). Changing it means **moving files** into a new directory
layout — a rewrite. Column mapping is by name/order with no stable id.

### 3. Metadata-level pruning → skip files without LISTing S3
The manifest stores each data file's **min/max stats and partition values**. For
`WHERE dt = '2024-01-01' AND amount > 1000`, the **query engine reads the
manifest** (a small file) and skips any data file whose `amount` max is below the
threshold — without opening it. It reads the **metadata inventory**, not an S3
`LIST`. (The catalog only gives the authoritative entry point — *which* metadata
is current; the engine does the pruning from that metadata, layer by layer:
manifest-list summary → manifest file stats → Parquet internal metadata.)

**Raw Parquet is slower:** the glob must first **LIST** S3 to expand the prefix
into a file list (slow and per-request-billed at thousands of prefixes), then
open each Parquet footer for stats. Iceberg precomputes "which files + each
file's stats" into the manifest, skipping both the LIST and the per-file probe.

### 4. Row-level DELETE / UPDATE / MERGE
The physical Parquet files stay immutable; what changes is the table's *logical*
result. Parquet itself provides no table-level update protocol — Iceberg supplies
one on top. Two strategies:
- **copy-on-write (CoW):** rewrite the affected files into new files; the new
  snapshot points at them; old files stay for history snapshots.
- **merge-on-read (MoR):** don't rewrite; write a small **delete file** ("row N
  of file X is deleted"); readers **overlay** it to filter at read time.
Either way, a new snapshot's manifest re-describes "the table = these data files
+ these delete files," and the commit is still that one atomic pointer swap.

**Raw Parquet can't:** a pile of `.parquet` + a glob has nowhere to express "this
row is deleted." Your only option is a full-file rewrite you manage by hand —
with no atomic commit, so concurrent readers see inconsistent state.

---

## The essence

These four are not four separate features — they are four consequences of **one
design**: *define "the table = which files" with an atomically-swappable,
statistics-carrying metadata layer.* Raw Parquet lacks that layer, so it can't
commit atomically (→ no ACID / time-travel / concurrency), has nowhere to store
an evolved schema (→ no evolution), nowhere to store per-file stats (→ LIST +
probe every file), and nowhere to mark "row deleted" (→ no row-level ops).

| Capability | Root cause (Why) |
|---|---|
| ACID / time-travel / concurrent writes | commit = **atomic pointer swap**; old snapshot's manifest retained |
| Schema/partition evolution | schema in **metadata + permanent field-ids**, not in file layout / directory path |
| Metadata pruning | manifest **pre-stores each file's min/max + partition values** → read the inventory, not LIST S3 |
| Row-level delete/update/MERGE | immutable files + **copy-on-write / delete-file**, then the atomic commit |

**DuckLake** is the same idea with a different catalog home (a SQL database
instead of `metadata.json` files), which is why it gives the same snapshots /
time-travel / row-level ops — and lets scenario 09 prove all of this **offline**.

## copy-on-write vs merge-on-read — how to choose

Both satisfy row-level delete/update; they trade **write cost** against **read
cost**.

| | copy-on-write (CoW) | merge-on-read (MoR) |
|---|---|---|
| On delete/update | rewrite the whole affected data file(s) | write a small delete file; data files untouched |
| Write cost | **high** (rewrite) | **low** (append a delete marker) |
| Read cost | **low** (no overlay) | **higher** (apply delete files at read) |
| Best for | read-heavy, infrequent small changes; batch nightly updates | write-heavy / streaming upserts, CDC, frequent small deletes |
| Cleanup | old files aged out by snapshot expiry | delete files periodically **compacted** back into data files |

Rule of thumb: **CoW when you read far more than you write** (analytics tables
updated in nightly batches); **MoR when you write/upsert frequently** (CDC,
streaming) and can afford a compaction job to keep read overlay small. Many
engines let you set this per table (`write.delete.mode` = `copy-on-write` /
`merge-on-read`). Scenario 09's `cow_vs_mor.py` shows the file-count signature of
each: after a delete, CoW's data `file_count` changes while MoR adds a
`delete_file_count`.

---

## Appendix — worked examples

Concrete illustrations for each principle. The read path of a catalog-backed
Iceberg table:

```
Catalog        : which metadata file `orders` currently points to
   ↓
Table metadata : schema, partition specs, current + historical snapshots
   ↓
Snapshot → manifest list : which manifests this version needs
   ↓
Manifests      : data/delete file lists, partition values, column stats
   ↓
Parquet data files + applicable delete records
```

**The key rule:** a file existing in a directory does not mean it belongs to the
table; being *referenced by a committed snapshot* is what makes it part of that
version. Everything below follows from this.

### 1. Atomic commit → ACID / concurrency / time-travel
Current snapshot `S0 → [A.parquet, B.parquet]`. An update that replaces `B` with
`B2`:
1. write `B2.parquet`; 2. write new metadata `S1 → [A.parquet, B2.parquet]`;
3. **atomically flip** the table's current-metadata pointer S0→S1.
- Before commit new readers see S0; after, S1; a query already reading S0 keeps
  reading S0. No "B deleted, B2 half-written" state; a failed write leaves
  unreferenced orphan files, not a broken table.
- **Concurrency = conditional swap** (compare-and-swap): "only flip to M1 if
  current is still the M0 I started from." Two writers off M0 — A commits first;
  B finds the version moved, must re-read and re-validate, then retry (or fail on
  a real conflict). Atomic swap prevents half-commits/overwrites; conflict
  validation decides whether concurrent ops merge safely (not all do).
- **Time-travel** comes for free: S0 and its files are retained, so "read current
  → follow S1", "read history → follow S0", with unchanged files/manifests shared
  across snapshots. Caveat: once old snapshots + their files are expired, that
  version is no longer readable; this is *single-table* commit, not cross-table.

### 2. Evolution without rewrite
- **Schema:** a column's identity is its **field-id**, not its name/position.
  `field-id 17 name customer_name` → rename → `field-id 17 name buyer_name`; old
  files still map field-17 data to the current name, no rewrite. Drop-then-add a
  same-named column → the new one gets a new id, so old data is never mistaken
  for it. (Add/drop/rename/reorder + supported type promotions — not arbitrary
  type casts — are metadata-only.)
- **Partition:** specs are versioned. `spec 0 = month(event_time)`,
  `spec 1 = day(event_time)` coexist; the engine derives predicates per spec (old
  files pruned by month, new by day). Changing the spec needs no rewrite; giving
  *old* data the new layout's performance still does.

### 3. Metadata pruning
Raw glob `s3://bucket/orders/*.parquet` must discover matching files then read
their metadata. Iceberg already recorded, per file, path + partition values +
column stats:
```
A.parquet : customer_id ∈ [1, 100]
B.parquet : customer_id ∈ [500, 900]
```
`WHERE customer_id = 700` → the manifest alone proves A can't match, so A is
never opened. Pruning cascades: manifest-list summary → skip manifests; manifest
stats → skip data files; Parquet internal metadata → locate within a file. Not
zero S3 requests and not always faster — with missing stats or heavily
overlapping ranges, pruning degrades.

### 4. Row-level ops — two strategies
- **Copy-on-write:** `A.parquet=[Alice,Bob,Carol]`, delete Bob → write
  `A2.parquet=[Alice,Carol]`; old snapshot → A, new snapshot → A2 (A untouched,
  just unreferenced). Cost: deleting one row can rewrite its whole file.
- **Merge-on-read:** data files untouched; write a **delete record** ("mask this
  row of A.parquet", or an equality delete "mask customer_id=42 in applicable
  files"). Readers apply deletes; Iceberg scopes them by partition/sequence-number
  so a later re-inserted same-value row isn't wrongly masked. `UPDATE` = mask old
  row + insert new row in one atomic commit; `MERGE` = engine computes the
  inserts/deletes/replacements then commits per protocol.

**One line:** Iceberg defines the table's logical state with versioned metadata
and publishes it with an atomic commit; the data files stay immutable. So the
real comparison is not *Iceberg vs Parquet* but **"a bare set of Parquet files"
vs "a Parquet table managed by Iceberg."**

*Sources: Apache Iceberg spec, reliability, evolution & spark-writes docs;
Apache Parquet file-format metadata docs.*
