import breakers


def test_max_steps_is_five():
    assert breakers.MAX_STEPS == 5


def test_cost_cap_breaks_at_five_steps():
    assert breakers.should_break(5, "a", "b", 0.0, 0.1) is True
    assert breakers.should_break(4, "a", "b", 0.0, 0.1) is False
