"""Scenario 08 governance matrix — all cells correct (regression guard, offline)."""
import importlib.util
import pathlib
import sys

MOD = (pathlib.Path(__file__).resolve().parents[1]
       / "scenarios" / "08_governance" / "matrix.py")


def _load():
    spec = importlib.util.spec_from_file_location("gov_matrix", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules["gov_matrix"] = m
    spec.loader.exec_module(m)
    return m


def test_matrix_all_cells_correct():
    m = _load()
    lines, ok, total = m.build_matrix()
    assert total > 0
    assert ok == total, f"{total - ok} governance-matrix cell(s) wrong"
