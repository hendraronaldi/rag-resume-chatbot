import breakers


def test_identical_tool_call_breaks():
    h = breakers.call_hash('{"name": "x", "email": "y"}')
    assert breakers.should_break(1, h, h, 0.0, 0.1) is True


def test_distinct_tool_call_continues():
    h1 = breakers.call_hash('{"name": "x"}')
    h2 = breakers.call_hash('{"name": "y"}')
    assert breakers.should_break(1, h1, h2, 0.0, 0.1) is False
