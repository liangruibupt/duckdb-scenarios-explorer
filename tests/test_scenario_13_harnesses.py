"""Scenario 13 -- offline checks for the ClickBench and Overture harnesses (no
downloads, no S3). They pin the parts that would silently skew results: the
ClickBench view is pointed at our file, macros survive, and every Overture query
template renders against the expected Parquet globs."""
import importlib.util
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
S13 = REPO / "scenarios" / "13_performance_benchmarks"


def _mod(name):
    sys.path.insert(0, str(S13))  # the harnesses import bench.py
    try:
        spec = importlib.util.spec_from_file_location(f"s13_{name}", S13 / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(S13))


CREATE = """CREATE VIEW hits AS
SELECT * REPLACE (make_date(EventDate) AS EventDate)
FROM read_parquet('hits.parquet', binary_as_string=True);

CREATE MACRO toDateTime(t) AS epoch_ms(t * 1000);
"""


def test_clickbench_view_points_at_local_file(tmp_path):
    m = _mod("clickbench")
    stmts = m.view_sql(CREATE, tmp_path / "hits.parquet")
    assert len(stmts) == 2
    assert f"'{(tmp_path / 'hits.parquet').as_posix()}'" in stmts[0]
    assert "'hits.parquet'" not in stmts[0]
    assert stmts[1].upper().startswith("CREATE MACRO")


def test_clickbench_split_and_summary():
    m = _mod("clickbench")
    assert m.split_sql("SELECT 1;\n\nSELECT 2;\n") == ["SELECT 1", "SELECT 2"]
    s = m.summarize([
        {"ok": True, "cold_seconds": 2.0, "hot_seconds": 1.0, "peak_rss_gb": 3.0},
        {"ok": False, "cold_seconds": None, "hot_seconds": None, "peak_rss_gb": 1.0},
    ])
    assert s == {"queries_ok": 1, "sum_cold_seconds": 2.0, "sum_hot_seconds": 1.0,
                 "max_peak_rss_gb": 3.0}


def test_clickbench_pinned_commit():
    m = _mod("clickbench")
    assert len(m.CLICKBENCH_SHA) == 40 and m.CLICKBENCH_SHA in m.RAW


def test_overture_queries_render(tmp_path):
    m = _mod("overture")
    g = m.globs("2026-10-21.0")
    assert g["buildings"].startswith("s3://overturemaps-us-west-2/release/2026-10-21.0/theme=buildings/")
    names = [q[0] for q in m.QUERIES]
    assert len(names) == len(set(names))
    for _, _, sql in m.QUERIES:
        rendered = sql.format(out=tmp_path.as_posix(), **g)
        assert "{" not in rendered and "read_parquet('s3://" in rendered
