#!/usr/bin/env python3
"""
Generate a self-contained HTML report (with inline SVG charts) from the
NYC taxi Parquet using DuckDB. No plotting library required -- charts are
hand-rendered SVG so the single .html file opens anywhere with zero assets.

Usage:  python report.py            # writes report.html
"""
from __future__ import annotations
import html
import duckdb

TRIPS = "read_parquet('data/yellow_2024-01.parquet')"
ZONES = "read_csv('data/taxi_zone_lookup.csv')"
OUT = "report.html"

# ---- tiny SVG chart helpers -------------------------------------------------

W, H, PAD = 720, 260, 40


def _axis(maxv: float):
    return (H - 2 * PAD) / maxv if maxv else 0


def bar_chart(labels, values, title, unit=""):
    maxv = max(values) or 1
    scale = _axis(maxv)
    n = len(values)
    bw = (W - 2 * PAD) / n * 0.72
    gap = (W - 2 * PAD) / n
    bars, ticks = [], []
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = PAD + i * gap + (gap - bw) / 2
        bh = v * scale
        y = H - PAD - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'rx="2" fill="#4c8bf5"><title>{html.escape(str(lab))}: {v:,.2f}{unit}</title></rect>'
        )
        if n <= 24 or i % 2 == 0:
            ticks.append(f'<text x="{x + bw/2:.1f}" y="{H - PAD + 14:.0f}" '
                         f'text-anchor="middle" font-size="10" fill="#666">{html.escape(str(lab))}</text>')
    grid = "".join(
        f'<line x1="{PAD}" y1="{H-PAD-frac*(H-2*PAD):.1f}" x2="{W-PAD}" '
        f'y2="{H-PAD-frac*(H-2*PAD):.1f}" stroke="#eee"/>'
        f'<text x="{PAD-6}" y="{H-PAD-frac*(H-2*PAD)+3:.1f}" text-anchor="end" '
        f'font-size="9" fill="#999">{maxv*frac:,.0f}</text>'
        for frac in (0, .25, .5, .75, 1)
    )
    return (f'<div class="chart"><h3>{html.escape(title)}</h3>'
            f'<svg viewBox="0 0 {W} {H}" width="100%">{grid}{"".join(bars)}{"".join(ticks)}</svg></div>')


def line_chart(labels, series, title):
    """series: list of (name, color, values)."""
    allv = [v for _, _, vals in series for v in vals]
    maxv, minv = max(allv), min(allv)
    rng = (maxv - minv) or 1
    n = len(labels)
    xstep = (W - 2 * PAD) / (n - 1 if n > 1 else 1)

    def pts(vals):
        return " ".join(
            f"{PAD + i*xstep:.1f},{H - PAD - (v-minv)/rng*(H-2*PAD):.1f}"
            for i, v in enumerate(vals))

    paths, legend = [], []
    for name, color, vals in series:
        paths.append(f'<polyline points="{pts(vals)}" fill="none" stroke="{color}" stroke-width="2"/>')
        legend.append(f'<span style="color:{color}">&#9632; {html.escape(name)}</span>')
    ticks = "".join(
        f'<text x="{PAD + i*xstep:.1f}" y="{H - PAD + 14:.0f}" text-anchor="middle" '
        f'font-size="9" fill="#666">{html.escape(str(labels[i]))}</text>'
        for i in range(0, n, max(1, n // 10)))
    return (f'<div class="chart"><h3>{html.escape(title)}</h3>'
            f'<div class="legend">{" &nbsp; ".join(legend)}</div>'
            f'<svg viewBox="0 0 {W} {H}" width="100%">{"".join(paths)}{ticks}</svg></div>')


def table(df, title):
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in df.itertuples(index=False))
    return (f'<div class="chart"><h3>{html.escape(title)}</h3>'
            f'<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')


# ---- build report -----------------------------------------------------------

def main() -> None:
    con = duckdb.connect()
    con.execute(f"""
        CREATE OR REPLACE VIEW clean AS
        SELECT * FROM {TRIPS}
        WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-01'
          AND tpep_pickup_datetime <  TIMESTAMP '2024-02-01'
          AND trip_distance > 0 AND trip_distance < 100
          AND fare_amount   > 0 AND fare_amount   < 500
          AND passenger_count BETWEEN 1 AND 6
          AND tpep_dropoff_datetime > tpep_pickup_datetime
    """)

    raw, clean = con.execute(
        f"SELECT (SELECT count(*) FROM {TRIPS}), (SELECT count(*) FROM clean)").fetchone()

    hourly = con.execute("""
        SELECT hour(tpep_pickup_datetime) AS hr, count(*) AS trips,
               avg(fare_amount) AS avg_fare, avg(tip_amount) AS avg_tip,
               avg(tip_amount)/avg(fare_amount)*100 AS tip_pct
        FROM clean GROUP BY hr ORDER BY hr
    """).fetchdf()

    zones = con.execute(f"""
        SELECT z.Zone, count(*) AS trips, round(avg(c.total_amount),2) AS avg_total
        FROM clean c JOIN {ZONES} z ON c.PULocationID=z.LocationID
        GROUP BY z.Zone ORDER BY trips DESC LIMIT 10
    """).fetchdf()

    daily = con.execute("""
        WITH d AS (SELECT tpep_pickup_datetime::DATE AS day, count(*) AS trips
                   FROM clean GROUP BY day)
        SELECT day, trips,
               avg(trips) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ma7
        FROM d ORDER BY day
    """).fetchdf()

    pay = con.execute("""
        SELECT CASE payment_type WHEN 1 THEN 'Credit' WHEN 2 THEN 'Cash'
                 WHEN 3 THEN 'No charge' WHEN 4 THEN 'Dispute' ELSE 'Other' END AS payment,
               count(*) AS trips
        FROM clean GROUP BY payment_type ORDER BY trips DESC
    """).fetchdf()

    charts = [
        bar_chart(hourly.hr.tolist(), hourly.trips.tolist(),
                  "Trips by hour of day"),
        line_chart(hourly.hr.tolist(),
                   [("avg fare $", "#4c8bf5", hourly.avg_fare.tolist()),
                    ("avg tip $", "#e07b39", hourly.avg_tip.tolist())],
                   "Average fare & tip by hour ($)"),
        bar_chart(hourly.hr.tolist(), hourly.tip_pct.tolist(),
                  "Tip % by hour", unit="%"),
        line_chart([str(d)[5:] for d in daily.day.tolist()],
                   [("daily trips", "#4c8bf5", daily.trips.tolist()),
                    ("7-day MA", "#2ca02c", daily.ma7.tolist())],
                   "Daily trips with 7-day moving average"),
        bar_chart(zones.Zone.tolist(), zones.trips.tolist(),
                  "Top 10 pickup zones by trips"),
        bar_chart(pay.payment.tolist(), pay.trips.tolist(),
                  "Payment type mix"),
        table(zones, "Top 10 pickup zones (detail)"),
    ]

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NYC Taxi Analytics -- DuckDB report</title>
<style>
  body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1c2530}}
  header{{background:#1c2530;color:#fff;padding:28px 32px}}
  header h1{{margin:0 0 4px;font-size:22px}} header p{{margin:0;color:#9fb0c3}}
  .wrap{{max-width:820px;margin:0 auto;padding:24px 16px}}
  .kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
  .kpi{{flex:1;min-width:140px;background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
  .kpi b{{display:block;font-size:24px;color:#1c2530}} .kpi span{{color:#6b7a8d;font-size:12px}}
  .chart{{background:#fff;border-radius:10px;padding:16px 18px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
  .chart h3{{margin:0 0 10px;font-size:15px}}
  .legend{{font-size:12px;margin-bottom:6px}}
  table{{border-collapse:collapse;width:100%;font-size:12px}}
  th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eef1f4}}
  th{{color:#6b7a8d;font-weight:600}}
  footer{{text-align:center;color:#9fb0c3;font-size:12px;padding:20px}}
</style></head><body>
<header><h1>NYC Yellow Taxi &mdash; January 2024</h1>
<p>Generated with DuckDB over a {raw:,}-row Parquet file. No database load step.</p></header>
<div class="wrap">
  <div class="kpis">
    <div class="kpi"><b>{raw:,}</b><span>raw trips</span></div>
    <div class="kpi"><b>{clean:,}</b><span>clean trips analysed</span></div>
    <div class="kpi"><b>{raw-clean:,}</b><span>rows dropped (bad data)</span></div>
    <div class="kpi"><b>{hourly.trips.sum()/31:,.0f}</b><span>avg trips / day</span></div>
  </div>
  {''.join(charts)}
</div>
<footer>Built with DuckDB {duckdb.__version__} &middot; inline SVG, zero chart dependencies</footer>
</body></html>"""

    with open(OUT, "w") as f:
        f.write(doc)
    print(f"Wrote {OUT} ({len(doc):,} bytes, {len(charts)} charts)")


if __name__ == "__main__":
    main()
