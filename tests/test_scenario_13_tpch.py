"""Scenario 13 -- TPC-H scale benchmark (offline, tiny SF). The load-bearing
invariants: the harness generates data, runs every requested query on both the
native file and Parquet views, every query matches the reference row count from
tpch_answers(), and it writes JSON + Markdown results."""
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
S13 = REPO / "scenarios" / "13_performance_benchmarks"


def _mod():
    spec = importlib.util.spec_from_file_location("s13", S13 / "bench.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_sf_label():
    m = _mod()
    assert m.sf_label(10) == "10"
    assert m.sf_label(0.1) == "0_1"


@pytest.mark.parametrize("source", ["native", "parquet"])
def test_benchmark_runs_and_matches_answers(tmp_path, source):
    pytest.importorskip("psutil")
    m = _mod()
    r = m.main(["--sf", "0.01", "--source", source, "--threads", "2",
                "--data-dir", str(tmp_path / "data"),
                "--results-dir", str(tmp_path / "res")])
    assert [q["query"] for q in r["queries"]] == list(range(1, 23))
    assert r["queries_ok"] == 22
    assert all(q["answer_rowcount_match"] for q in r["queries"])
    assert all(q["seconds"] >= 0 and q["peak_rss_gb"] > 0 for q in r["queries"])
    stem = tmp_path / "res" / f"sf0_01_{source}"
    saved = json.loads(stem.with_suffix(".json").read_text())
    assert saved["total_seconds"] == r["total_seconds"]
    md = stem.with_suffix(".md").read_text()
    assert "| Q01 |" in md and "| Q22 |" in md
    if source == "parquet":
        assert len(list((tmp_path / "data" / "tpch_sf0_01_parquet").glob("*.parquet"))) == 8


def test_query_subset(tmp_path):
    pytest.importorskip("psutil")
    m = _mod()
    r = m.main(["--sf", "0.01", "--queries", "1,6", "--threads", "1",
                "--data-dir", str(tmp_path / "data"),
                "--results-dir", str(tmp_path / "res")])
    assert [q["query"] for q in r["queries"]] == [1, 6]
