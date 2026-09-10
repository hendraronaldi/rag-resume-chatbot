import staleness


def test_index_build_date_injected_into_prompt():
    assert staleness.INDEX_BUILD_DATE in staleness.build_system_prompt()


def test_post_date_question_refused():
    assert "do not have that information yet" in staleness.answer_for_event_date("2026-09-01")


def test_pre_date_question_answered():
    assert "do not have that information yet" not in staleness.answer_for_event_date("2026-07-01")
