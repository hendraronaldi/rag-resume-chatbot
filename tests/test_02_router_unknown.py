import pytest

import router


class _FailingLLM:
    def complete(self, prompt, **kwargs):
        raise ConnectionError("provider down")


class _JsonLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, prompt, **kwargs):
        return self.text


def test_blank_query_rejected():
    with pytest.raises(router.Unroutable):
        router.route("   ")


def test_oversize_query_rejected():
    with pytest.raises(router.Unroutable):
        router.route("x" * 2001)


def test_llm_failure_falls_back_to_regex_result():
    assert router.route_with_llm(
        "What programming languages are listed on the resume?",
        _FailingLLM(),
    ) == router.RAG
    assert router.route_with_llm(
        "Hello! Who am I chatting with?", _FailingLLM()
    ) == router.CHAT
    assert router.route_with_llm(
        "Reach me at jane.doe@example.com please.", _FailingLLM()
    ) == router.LEAD_CAPTURE


def test_llm_json_intent_wins_over_regex():
    assert router.route_with_llm(
        "What programming languages are listed on the resume?",
        _JsonLLM('{"intent": "CHAT"}'),
    ) == router.CHAT


def test_llm_garbage_falls_back_to_regex():
    assert router.route_with_llm(
        "Hello! Who am I chatting with?", _JsonLLM("not an intent")
    ) == router.CHAT


def test_llm_path_rejects_unroutable_before_provider_call():
    with pytest.raises(router.Unroutable):
        router.route_with_llm("   ", _FailingLLM())


def test_opportunity_offer_routes_to_lead_capture():
    assert router.route("We have a job offer for you, let's talk.") == router.LEAD_CAPTURE
    assert router.route("Interested in a partnership with our team?") == router.LEAD_CAPTURE
    assert router.route("Want to collaborate on a freelance project?") == router.LEAD_CAPTURE
    assert router.route("We are hiring, join our team!") == router.LEAD_CAPTURE


def test_role_mention_without_offer_stays_rag():
    assert router.route("Compare the two most recent roles by scope and stack.") == router.RAG


def test_other_accepted_from_llm_only():
    assert router.route_with_llm(
        "What is the capital of France?", _JsonLLM('{"intent": "OTHER"}')
    ) == router.OTHER
    assert router.route("What is the capital of France?") == router.RAG
