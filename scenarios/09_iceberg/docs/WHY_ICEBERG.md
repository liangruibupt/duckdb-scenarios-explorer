# Why Iceberg can do what raw Parquet cannot

One sentence: **Parquet is "files"; Iceberg is "a layer of atomically-swappable
metadata that points at those files."** Every capability below falls out of that
one design — a versioned, statistics-carrying metadata layer that *defines which
files make up the table*, instead of letting a glob guess it at query time.

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
`WHERE dt = '2024-01-01' AND amount > 1000`, the engine **reads the manifest**
(a small file) and skips any data file whose `amount` max is below the threshold
— without opening it. It reads the **metadata inventory**, not an S3 `LIST`.

**Raw Parquet is slower:** the glob must first **LIST** S3 to expand the prefix
into a file list (slow and per-request-billed at thousands of prefixes), then
open each Parquet footer for stats. Iceberg precomputes "which files + each
file's stats" into the manifest, skipping both the LIST and the per-file probe.

### 4. Row-level DELETE / UPDATE / MERGE → impossible on raw Parquet
Parquet files are **immutable** (changing one row means rewriting the whole
file). Iceberg expresses delete/update on immutable files two ways:
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
