#!/usr/bin/env bash
# Seed scenario 02's S3 data ONCE. Run this in a terminal with AWS creds that
# can write to the bucket (the Kiro Crew agent is blocked from S3 writes).
#
#   ./seed_s3.sh                     # uses local ../01_nyc_taxi/data/*.parquet
#
# Lays the file out hive-partitioned so DuckDB can prune on year=/month=:
#   s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/year=2024/month=01/part.parquet
set -euo pipefail
BUCKET="cdh-ingest-demo"
PREFIX="duckdb-demo/nyc_taxi"
SRC="../01_nyc_taxi/data/yellow_2024-01.parquet"

[ -f "$SRC" ] || { echo "Missing $SRC -- run ../01_nyc_taxi/get_data.sh first"; exit 1; }

aws s3 cp "$SRC" \
  "s3://${BUCKET}/${PREFIX}/year=2024/month=01/part.parquet"

echo "Seeded s3://${BUCKET}/${PREFIX}/year=2024/month=01/part.parquet"
echo "Now run:  python remote_parquet.py"
