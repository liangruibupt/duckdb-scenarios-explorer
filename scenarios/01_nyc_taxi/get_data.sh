#!/usr/bin/env bash
# Download the public NYC TLC data for scenario 01 (not committed -- ~48MB).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
base="https://d37ci6vzurychx.cloudfront.net"
[ -f data/yellow_2024-01.parquet ] || \
  curl -fSL -o data/yellow_2024-01.parquet "$base/trip-data/yellow_tripdata_2024-01.parquet"
[ -f data/taxi_zone_lookup.csv ] || \
  curl -fSL -o data/taxi_zone_lookup.csv "$base/misc/taxi_zone_lookup.csv"
echo "Data ready in ./data"
