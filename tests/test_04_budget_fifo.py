import budget


def test_lowest_ranked_chunks_dropped_first():
    chunks = [{"rank": 1, "text": "keep me"},
              {"rank": 9, "text": "drop me " * 40}]
    ctx = budget.assemble_context("sys", "q", chunks, [], 12)
    assert [c["rank"] for c in ctx["chunks"]] == [1]


def test_history_evicted_oldest_first():
    history = ["oldest", "middle", "newest"]
    ctx = budget.assemble_context("sys", "q", [], history, 4)
    assert ctx["history"][0] != "oldest"
    assert ctx["history"][-1] == "newest"
