# TPC-H SF1.0 · source = parquet

- Machine: m8g.xlarge: 4 vCPU, 15.3 GB RAM, aarch64, DuckDB 2.0.0
- Settings: memory_limit=10GB, threads=4
- Data: generation reused an existing file; database file 0.26 GB; Parquet 0.21 GB
- Total query time: 1.3 s (22/22 queries succeeded)

| Query | Seconds | Peak RSS (GB) | Peak buffer (GB) | Peak spill (GB) | Status |
|---|---:|---:|---:|---:|---|
| Q01 | 0.07 | 0.13 | 0.00 | 0.00 | ok |
| Q02 | 0.02 | 0.15 | 0.00 | 0.00 | ok |
| Q03 | 0.06 | 0.18 | 0.00 | 0.00 | ok |
| Q04 | 0.03 | 0.18 | 0.00 | 0.00 | ok |
| Q05 | 0.06 | 0.20 | 0.00 | 0.00 | ok |
| Q06 | 0.03 | 0.20 | 0.00 | 0.00 | ok |
| Q07 | 0.06 | 0.21 | 0.00 | 0.00 | ok |
| Q08 | 0.07 | 0.22 | 0.00 | 0.00 | ok |
| Q09 | 0.12 | 0.27 | 0.13 | 0.00 | ok |
| Q10 | 0.09 | 0.28 | 0.00 | 0.00 | ok |
| Q11 | 0.01 | 0.27 | 0.00 | 0.00 | ok |
| Q12 | 0.04 | 0.27 | 0.00 | 0.00 | ok |
| Q13 | 0.11 | 0.32 | 0.09 | 0.00 | ok |
| Q14 | 0.05 | 0.31 | 0.00 | 0.00 | ok |
| Q15 | 0.04 | 0.30 | 0.00 | 0.00 | ok |
| Q16 | 0.03 | 0.29 | 0.00 | 0.00 | ok |
| Q17 | 0.07 | 0.29 | 0.00 | 0.00 | ok |
| Q18 | 0.08 | 0.28 | 0.00 | 0.00 | ok |
| Q19 | 0.07 | 0.26 | 0.00 | 0.00 | ok |
| Q20 | 0.05 | 0.26 | 0.00 | 0.00 | ok |
| Q21 | 0.10 | 0.26 | 0.02 | 0.00 | ok |
| Q22 | 0.04 | 0.25 | 0.00 | 0.00 | ok |
