import tracing


def _recorded():
    rec = tracing.Recorder()
    rec.span("router", tokens=120, latency_ms=210.5)
    rec.span("retrieval", tokens=800, latency_ms=95.0)
    rec.span("generation", tokens=350, latency_ms=1100.0)
    return rec


def test_spans_carry_costs_and_latencies():
    assert _recorded().shape_ok() is True


def test_keyed_mode_builds_valid_payload_or_degrades():
    if tracing.keyed_mode():
        event = tracing.ingestion_event(_recorded())
        assert event["traceId"]
        assert {s["name"] for s in event["spans"]} == set(tracing.REQUIRED_SPANS)
    else:
        assert tracing.live_post_enabled() is False


def test_sink_event_builds_v4_observation_specs():
    rec = _recorded()
    record = {"trace_id": rec.trace_id,
              "intent": "RAG",
              "query": "q",
              "answer": "a",
              "spans": rec.spans,
              "user_id": "user-123",
              "session_id": "session-456",
              "index_build_date": "2026-08-01"}
    specs = tracing.sink_event(record)
    assert [s["name"] for s in specs] == (
        ["rag-chat [RAG]"] + list(tracing.REQUIRED_SPANS))
    root, children = specs[0], specs[1:]
    assert root["user_id"] == "user-123"
    assert root["session_id"] == "session-456"
    assert root["trace_name"] == "rag-chat [RAG]"
    assert root["tags"] == ["RAG"]
    by_name = {s["name"]: s for s in children}
    assert by_name["generation"]["as_type"] == "generation"
    assert by_name["router"]["as_type"] == "span"
    for spec in specs:
        for value in spec["metadata"].values():
            assert isinstance(value, str)
            assert len(value) <= 200


def test_sink_event_drops_overlong_ids_and_metadata():
    rec = _recorded()
    record = {"trace_id": rec.trace_id,
              "spans": rec.spans,
              "user_id": "u" * 201,
              "session_id": "s" * 201}
    specs = tracing.sink_event(record)
    assert specs
    assert specs[0]["user_id"] is None
    assert specs[0]["session_id"] is None
    assert tracing.sink_event({}) == []
    assert tracing.sink_event({"trace_id": "", "spans": []}) == []
