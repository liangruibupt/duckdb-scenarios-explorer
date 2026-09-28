# Deployment record — S3 Tables Iceberg (scenarios 02 path B + 09 cloud)

Created 2026-09-28, account **747411437379**, us-east-1.

## Live resources

| Resource | Identifier |
|----------|-----------|
| S3 Tables bucket | `arn:aws:s3tables:us-east-1:747411437379:bucket/duckdb-scenarios-iceberg` |
| Namespace | `nyc` |
| Iceberg table | `nyc.trips` — 501,000 rows (500k initial + 1k appended = 2 snapshots) |

Written by **DuckDB via the S3 Tables Iceberg REST catalog** (`ATTACH … TYPE
iceberg, ENDPOINT_TYPE s3_tables`) from the taxi Parquet — no Spark, no Glue job.

## Verified (live)

- `scenarios/09_iceberg/cloud_s3tables.py` — reads the managed table in place:
  501,000 rows, per-payment aggregate.
- `scenarios/02_httpfs_s3/remote_parquet.py` **path B** (`S3_TABLES_ARN=… ICEBERG_TABLE=nyc.trips`)
  — the same aggregate over the Iceberg table (319 ms), beside path A (raw
  Parquet). Same answer, same governance, different resolution.

## How to run against it
```
export S3_TABLES_ARN=arn:aws:s3tables:us-east-1:747411437379:bucket/duckdb-scenarios-iceberg
export ICEBERG_TABLE=nyc.trips
python scenarios/09_iceberg/cloud_s3tables.py
python scenarios/02_httpfs_s3/remote_parquet.py     # now runs path B too
```

## Cost
S3 Tables storage + maintenance (compaction) for a ~500k-row table — small,
storage-class billing. No compute runs when idle.

## Teardown (boto3)
1. `s3tables delete_table --table-bucket-arn <arn> --namespace nyc --name trips`
2. `s3tables delete_namespace --table-bucket-arn <arn> --namespace nyc`
3. `s3tables delete_table_bucket --table-bucket-arn <arn>`
