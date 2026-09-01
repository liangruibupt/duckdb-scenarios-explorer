"""Scenario 07 -- multi-agent embedded DuckDB invariants (offline)."""
import importlib.util
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MOD = REPO / "scenarios" / "07_multiagent_agentcore" / "agent_query.py"


def _load():
    spec = importlib.util.spec_from_file_location("agent_query", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


aq = _load()
DAYS, PER_DAY = 4, 5_000


@pytest.fixture(scope="module")
def lake(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("lake") / "events")
    aq.build_local_lake(root, days=DAYS, per_day=PER_DAY)
    return root


def test_each_agent_has_own_connection(lake):
    a, b = aq.Agent(0, lake), aq.Agent(1, lake)
    assert a.con is not b.con


def test_concurrent_agents_return_identical_results(lake):
    results = aq.fan_out(lake, n_agents=8)
    assert len(results) == 8
    assert all(r == results[0] for r in results)   # no contention, same data


def test_aggregate_counts_match_rows_written(lake):
    res = aq.Agent(0, lake).revenue_by_region()
    total_events = sum(n for n, _ in res.values())
    assert total_events == DAYS * PER_DAY


def test_partition_pruned_read_returns_one_day(lake):
    assert aq.Agent(0, lake).one_day("2024-01-02") == PER_DAY


def test_revenue_is_positive_per_region(lake):
    res = aq.Agent(0, lake).revenue_by_region()
    assert len(res) == 5
    assert all(rev > 0 for _, rev in res.values())
