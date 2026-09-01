# duckdb-scenarios-explorer

A growing collection of hands-on scenarios that show where **DuckDB** shines:
in-process, columnar, vectorized analytics (OLAP) over files — Parquet, CSV,
JSON, DataFrames, and remote object storage — with **no server and no load step**.

Each scenario is self-contained under `scenarios/<NN_name>/` with its own
runnable scripts. See **[SCENARIOS.md](SCENARIOS.md)** for the catalog and the
status of each one.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Scenario 01 — NYC taxi analytics
cd scenarios/01_nyc_taxi
./get_data.sh          # downloads ~48MB public Parquet + zone CSV (not committed)
python analytics.py    # 6 analytical queries over ~3M rows
python benchmark.py    # DuckDB vs Pandas on the same aggregate
python report.py       # -> report.html (self-contained, inline-SVG charts)
```

## Why DuckDB for these

- **No ETL to start**: query a Parquet/CSV/JSON file directly with SQL.
- **Columnar + vectorized**: reads only the columns a query touches; predicate
  and projection push-down into Parquet.
- **Embedded**: a library in your process (Python/CLI/WASM), not a service to
  operate — zero infra, zero idle cost.
- **Real SQL**: window functions, exact & approximate quantiles, `httpfs` for
  S3/HTTP, joins across heterogeneous file formats.

## Repo layout

```
scenarios/
  01_nyc_taxi/        analytics + benchmark + HTML report   [implemented]
  ...                 (see SCENARIOS.md for the roadmap)
requirements.txt
SCENARIOS.md
```
