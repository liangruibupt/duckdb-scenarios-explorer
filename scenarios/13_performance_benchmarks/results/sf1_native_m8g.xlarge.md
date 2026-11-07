# TPC-H SF1.0 · source = native

- Machine: m8g.xlarge: 4 vCPU, 15.3 GB RAM, aarch64, DuckDB 2.0.0
- Settings: memory_limit=10GB, threads=4
- Data: generation reused an existing file; database file 0.26 GB; Parquet - GB
- Total query time: 0.6 s (22/22 queries succeeded)

| Query | Seconds | Peak RSS (GB) | Peak buffer (GB) | Peak spill (GB) | Status |
|---|---:|---:|---:|---:|---|
| Q01 | 0.04 | 0.13 | 0.05 | 0.00 | ok |
| Q02 | 0.01 | 0.15 | 0.06 | 0.00 | ok |
| Q03 | 0.03 | 0.18 | 0.08 | 0.00 | ok |
| Q04 | 0.02 | 0.20 | 0.10 | 0.00 | ok |
| Q05 | 0.03 | 0.22 | 0.11 | 0.00 | ok |
| Q06 | 0.01 | 0.22 | 0.11 | 0.00 | ok |
| Q07 | 0.02 | 0.24 | 0.11 | 0.00 | ok |
| Q08 | 0.02 | 0.25 | 0.12 | 0.00 | ok |
| Q09 | 0.06 | 0.26 | 0.13 | 0.00 | ok |
| Q10 | 0.04 | 0.27 | 0.14 | 0.00 | ok |
| Q11 | 0.01 | 0.27 | 0.14 | 0.00 | ok |
| Q12 | 0.02 | 0.27 | 0.14 | 0.00 | ok |
| Q13 | 0.08 | 0.31 | 0.16 | 0.00 | ok |
| Q14 | 0.02 | 0.31 | 0.16 | 0.00 | ok |
| Q15 | 0.01 | 0.31 | 0.16 | 0.00 | ok |
| Q16 | 0.03 | 0.32 | 0.16 | 0.00 | ok |
| Q17 | 0.02 | 0.32 | 0.16 | 0.00 | ok |
| Q18 | 0.05 | 0.34 | 0.16 | 0.00 | ok |
| Q19 | 0.02 | 0.34 | 0.16 | 0.00 | ok |
| Q20 | 0.02 | 0.34 | 0.16 | 0.00 | ok |
| Q21 | 0.04 | 0.34 | 0.16 | 0.00 | ok |
| Q22 | 0.02 | 0.34 | 0.16 | 0.00 | ok |
