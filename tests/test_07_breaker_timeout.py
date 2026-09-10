import breakers


def test_time_budget_is_sixty_seconds():
    assert breakers.TIME_BUDGET_S == 60.0


def test_over_budget_breaks():
    assert breakers.should_break(1, "a", "b", 0.0, 60.01) is True
    assert breakers.should_break(1, "a", "b", 0.0, 59.99) is False
