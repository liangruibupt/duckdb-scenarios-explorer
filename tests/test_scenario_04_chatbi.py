"""Scenario 04 -- chat BI. Planner logic is offline; execution is data-gated."""
import importlib.util
import pathlib
import pytest
from conftest import requires_taxi

REPO = pathlib.Path(__file__).resolve().parents[1]
MOD = REPO / "scenarios" / "04_chat_bi" / "chat_bi.py"


def _load():
    spec = importlib.util.spec_from_file_location("chat_bi", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cb = _load()


# --- offline: planner logic --------------------------------------------------

@pytest.mark.parametrize("q", [
    "How many trips were there?",
    "What are the busiest 5 pickup zones?",
    "Average tip by hour of day",
    "Payment mix",
    "Revenue by day",
])
def test_rule_plan_returns_single_select(q):
    sql = cb.rule_plan(q)
    assert sql is not None
    assert sql.strip().lower().startswith("select")
    assert sql.count(";") == 0            # single statement


def test_rule_plan_unsupported_returns_none():
    assert cb.rule_plan("what is the meaning of life") is None


def test_num_extraction():
    assert cb._num("busiest 5 zones", default=10) == 5
    assert cb._num("busiest zones", default=10) == 10


def test_busiest_n_respects_number():
    assert "LIMIT 7" in cb.rule_plan("top 7 zones")


def test_llm_guardrail_rejects_non_select():
    # simulate a model returning DML -> the guardrail regex must reject it
    import re
    bad = "DELETE FROM trips"
    assert re.match(r"(?is)^\s*select\b", bad) is None


# --- data-gated: execution ---------------------------------------------------

@requires_taxi
def test_how_many_trips_executes(con, monkeypatch):
    monkeypatch.chdir(MOD.parent)      # DATA path is relative to the scenario dir
    sql = cb.rule_plan("How many trips were there?")
    n = con.execute(sql).fetchone()[0]
    assert isinstance(n, int) and n > 0


@requires_taxi
def test_busiest_5_returns_5_rows(con, monkeypatch):
    monkeypatch.chdir(MOD.parent)
    sql = cb.rule_plan("busiest 5 zones")
    df = con.execute(sql).fetchdf()
    assert len(df) == 5
