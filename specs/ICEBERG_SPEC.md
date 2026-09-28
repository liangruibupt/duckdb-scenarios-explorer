# Iceberg pass — spec

The aws-sample treats Iceberg (S3 Tables / Glue REST) as first-class because a
raw Parquet glob is immutable and catalog-less. This pass adds the table-format
capabilities across the repo. AI-DLC contract for `tests/`.

## Engine facts (probed, DuckDB 1.5.5)
- `iceberg` extension, **two modes**:
  - `iceberg_scan('<metadata location>')` is **read-only** — scans an existing
    Iceberg table's files; it does not create or mutate a table.
  - `ATTACH '<arn>' AS c (TYPE iceberg, ENDPOINT_TYPE s3_tables)` attaches the
    **S3 Tables Iceberg REST catalog**, which **does support writes** from DuckDB:
    `CREATE TABLE … AS`, `INSERT` (each a new snapshot) — verified live by
    creating + appending `nyc.trips` on S3 Tables (no Spark/Glue). Update/delete
    depend on the catalog/extension version; treat as append-first.
  - `iceberg_snapshots` / `iceberg_metadata` read the snapshot history.
- `ducklake` = a full **read/write** Iceberg-style table format (SQL catalog +
  Parquet data), fully local. It gives ACID snapshots, **time-travel**
  (`AT (VERSION => n)`), **schema evolution** (`ALTER TABLE … ADD COLUMN`), and
  **row-level UPDATE/DELETE** — the differentiators, testable OFFLINE.

So: **offline** capability demos use DuckLake (full read/write incl.
update/delete); **cloud** uses a real **S3 Tables** Iceberg table — DuckDB both
**writes** it (create + append via the REST catalog) and reads it in place.

## Test tiers
- **offline**: DuckLake create/insert/update/delete/alter/time-travel; iceberg
  extension loads; governance over an iceberg-shaped source. CI-run.
- **cloud/iceberg-gated**: create/append + read a real S3 Tables Iceberg table
  via the REST catalog, and `iceberg_scan` of a metadata location — skipped
  unless `RUN_ICEBERG_TESTS=1`.

---

## 09 — Iceberg / DuckLake table differentiators (NEW)
`scenarios/09_iceberg/tables.py` — a self-contained DuckLake demo proving what raw
Parquet cannot:
- **time-travel**: query a table `AT (VERSION => n)` before an update/delete.
- **schema evolution**: `ADD COLUMN`; older snapshots still read.
- **row-level ops**: `UPDATE`/`DELETE` a subset (impossible on immutable Parquet).
- **snapshots**: `ducklake_snapshots()` lists the commit history.
Invariants: post-update current != AS-OF-prior; row count after DELETE < before;
an added column is NULL in pre-evolution snapshots; snapshot count increases per
commit.

## 02 — add an Iceberg access path
`remote_parquet.py` gains an `iceberg_scan('s3://…')` path beside the raw glob,
mirroring the sample's path A (raw) / path B (Iceberg). Cloud/iceberg-gated;
offline test asserts the iceberg extension loads and the code selects the right
path by env.

## 03 — CSV → managed table ETL
`etl.py` gains a DuckLake output target (`--target ducklake`): the same clean/cast
then written to a **managed table** (append = new snapshot), re-queried by
time-travel. Parquet target kept as the compatibility variant. Invariant: two
appends produce two snapshots; each is independently time-travellable.

## 06 — log analytics with time-travel
`log_analytics.py` gains a DuckLake mode: append the NDJSON per-minute rollups as
snapshots, then answer "what did the table look like before the 14:10 spike?" via
time-travel. Invariant: the AS-OF-pre-spike snapshot lacks the spike minutes.

## 07 — design update
DESIGN.md: the shared read layer is **Iceberg on S3** (S3 Tables), not just raw
Parquet — concurrent-writer safety + snapshot isolation is the reason a
multi-agent fleet needs a table format, not a file glob.

## 08 — governance across the iceberg path
matrix.py gains an `iceberg` access-path column; the governance rewrite must be
identical on the iceberg path (name-based, format-agnostic). Matrix stays 100%.
