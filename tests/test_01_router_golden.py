import json
import os

import router

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "fixtures", "golden_router.json")


def test_intent_router_golden_set_100_percent():
    with open(GOLDEN) as fh:
        cases = json.load(fh)
    assert len(cases) == 30
    mismatches = [(c["q"], c["expected"], router.route(c["q"]))
                  for c in cases
                  if router.route(c["q"]) != c["expected"]]
    assert mismatches == []
