import json
import os

import retrieval

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "fixtures", "golden_retrieval.json")


def test_hit_rate_at_3_above_90_percent():
    with open(GOLDEN) as fh:
        cases = json.load(fh)
    assert len(cases) == 20
    hits = sum(1 for c in cases
               if set(retrieval.retrieve(c["q"], k=3)) & set(c["expected_chunk_ids"]))
    assert hits / len(cases) > 0.90
