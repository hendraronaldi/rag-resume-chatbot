import pytest

import budget


def test_p1_overflow_returns_400():
    with pytest.raises(budget.BudgetExceeded):
        budget.assemble_context("word " * 50, "word " * 60, [], [], 100)


def test_p1_never_dropped_when_fitting():
    ctx = budget.assemble_context("sys", "query",
                                  [{"rank": 1, "text": "chunk"}],
                                  ["old", "new"], 100)
    assert ctx["system"] == "sys"
    assert ctx["query"] == "query"
