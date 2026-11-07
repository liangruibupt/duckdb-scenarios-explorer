#!/usr/bin/env bash
# Run the full scale ladder used for results/: SF1 and SF10 on both sources,
# then SF100 on the native file only (its Parquet copy would need another
# ~25 GB of disk). Deletes SF10 data before SF100 to keep disk use bounded.
# Needs roughly 45 GB free disk for SF100 (≈26 GB database + spill headroom).
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python}
MEM=${MEMORY_LIMIT:-10GB}
THREADS=${THREADS:-$(nproc)}

for sf in 1 10; do
  "$PY" bench.py --sf "$sf" --memory-limit "$MEM" --threads "$THREADS"
  "$PY" bench.py --sf "$sf" --source parquet --memory-limit "$MEM" --threads "$THREADS"
done
rm -rf data/tpch_sf10.duckdb data/tpch_sf10_parquet data/tmp_sf10 data/tpch_sf1_parquet

"$PY" bench.py --sf 100 --memory-limit "$MEM" --threads "$THREADS" \
  --max-temp "${MAX_TEMP:-15GB}"
