"""Tier 3 generation eval: slow LLM-as-a-judge scoring (guide 03, Tier 3).

MANUAL-ONLY, LOCAL-ONLY. This script is NEVER a per-change gate:

- pytest does not collect it (``eval_`` prefix, not ``test_``).
- No CI config references it. Run it by hand when release quality matters:
    python eval_judge.py [--answers answers.json] [--strict]

What it scores (spec: groundedness + professional tone, 0 hallucination
regressions on critical facts):

- Groundedness: fraction of answer content-words present in the retrieved
  top-k chunks (heuristic stand-in for the LLM judge; no network, no API key).
- Professional tone: deterministic checks (no shouting/profanity, ends with
  terminal punctuation, sane length).
- Critical facts: every golden question's expected chunk must be present in
  the retrieved top-k, otherwise the answer cannot be grounded in it. Misses
  are reported; ``--strict`` turns them into a non-zero exit.

Answer source (default): extractive stub answers (top-1 retrieved chunk text,
grounded by construction) so the script runs fully offline. To judge live
endpoint answers instead, capture them into JSON and pass ``--answers``:

    [{"q": "...", "answer": "...", "expected_chunk_ids": ["c01"]}]

If ``--answers`` entries omit expectations, they are resolved by exact
question match against the retrieval fixture, then the generation fixture.

Live collection (real stack, real resume data): ``--collect`` queries a
running backend (``POST {base}/query-resume/``) for every question in
``fixtures/golden_generation.json`` — factual questions grounded in
``app/data/resume.md`` with expected keywords — and judges the live replies
with the keyword verdict (every required keyword must appear verbatim,
case-insensitive). This is the only mode that can catch real regressions
(stale index, bad resume edit, broken prompt); stub mode only proves the
harness runs. Collection needs the backend up (``uvicorn main:app``) and,
for non-stub replies, a configured LLM key. Still manual-only: nothing here
is collected by pytest or referenced by any CI config.

Exit codes: 0 = pass (no hallucination regressions under the selected mode),
1 = fail. Human LLM review of flagged answers is always the final word.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import retrieval

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden_retrieval.json"
)
GENERATION_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden_generation.json"
)

PROFANITY = frozenset(
    "damn hell crap stupid dumb idiot hate sucks suck".split()
)

_SENTENCE_END = re.compile(r"[.!?][\"']?\s*$")


def load_golden(path: str = FIXTURE) -> List[Dict[str, Any]]:
    """Load the 20-question factual golden set.

    Args:
        path: Path to the golden retrieval fixture.

    Returns:
        List of golden cases with ``q`` and ``expected_chunk_ids`` keys.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_generation(path: str = GENERATION_FIXTURE) -> List[Dict[str, Any]]:
    """Load the resume-grounded generation golden set.

    Args:
        path: Path to the golden generation fixture.

    Returns:
        List of cases with ``q``, ``expected_keywords`` and optional
        ``expected_any`` (at least one must appear) keys.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_stub_answer(question: str, k: int = 3) -> Dict[str, Any]:
    """Build an extractive stub answer for offline judging.

    Args:
        question: The factual question to answer.
        k: Number of chunks retrieved for grounding context.

    Returns:
        Dict with question, answer, retrieved chunk ids and texts.
    """
    top_ids = retrieval.retrieve(question, k=k)
    texts = [retrieval.CHUNKS[cid] for cid in top_ids]
    answer = texts[0] if texts else ""
    return {
        "q": question,
        "answer": answer,
        "retrieved_chunk_ids": top_ids,
        "retrieved_texts": texts,
    }


def judge_groundedness(answer: str, retrieved_texts: List[str]) -> float:
    """Score groundedness as content-word overlap with retrieved chunks.

    Args:
        answer: Candidate answer text.
        retrieved_texts: Chunk texts retrieved for the question.

    Returns:
        Fraction of answer content-words present in the retrieved token set
        (1.0 when the answer is empty of content words to avoid div-by-zero).
    """
    answer_tokens = retrieval.tokenize(answer or "")
    if not answer_tokens:
        return 1.0
    context_tokens = set()
    for text in retrieved_texts:
        context_tokens |= retrieval.tokenize(text)
    if not context_tokens:
        return 0.0
    return len(answer_tokens & context_tokens) / len(answer_tokens)


def judge_tone(answer: str) -> Dict[str, Any]:
    """Score professional tone with deterministic checks.

    Args:
        answer: Candidate answer text.

    Returns:
        Dict with per-check booleans and an overall ``pass`` flag.
    """
    text = answer or ""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    checks = {
        "non_empty": bool(text.strip()),
        "no_shouting": text != "" and sum(1 for c in text if c.isupper()) < max(8, len(text) // 2),
        "no_profanity": not (set(words) & PROFANITY),
        "ends_with_punctuation": bool(_SENTENCE_END.search(text.strip())),
        "sane_length": 20 <= len(text) <= 2000,
    }
    checks["pass"] = all(checks.values())
    return checks


def judge_case(
    question: str,
    answer: str,
    expected_chunk_ids: Optional[List[str]] = None,
    retrieved_ids: Optional[List[str]] = None,
    retrieved_texts: Optional[List[str]] = None,
    expected_keywords: Optional[List[str]] = None,
    expected_any: Optional[List[str]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Judge a single question/answer pair.

    Two verdict shapes: chunk-grounded (stub mode and chunk-keyed external
    answers) and keyword-grounded (live generation answers). A case uses the
    keyword verdict whenever ``expected_keywords``/``expected_any`` is set.

    Args:
        question: The factual question asked.
        answer: The answer under judgment.
        expected_chunk_ids: Golden chunk ids that ground the answer.
        retrieved_ids: Chunk ids retrieved for the question.
        retrieved_texts: Corresponding chunk texts.
        expected_keywords: Required keywords; all must appear verbatim
            (case-insensitive) in the answer.
        expected_any: Alternative keywords; at least one must appear.
        error: Collection error, if the answer never arrived.

    Returns:
        Dict with groundedness, tone, critical-fact verdict and details.
    """
    expected_chunk_ids = expected_chunk_ids or []
    retrieved_ids = retrieved_ids or []
    retrieved_texts = retrieved_texts or []
    tone = judge_tone(answer)
    if expected_keywords or expected_any:
        return _judge_keywords(
            question, answer, expected_keywords or [], expected_any or [], tone,
            error=error,
        )
    groundedness = judge_groundedness(answer, retrieved_texts)
    critical_present = bool(set(retrieved_ids) & set(expected_chunk_ids))
    # A hallucination regression is either a missing critical fact (the
    # retrieved context cannot ground the answer) or an answer whose words
    # are mostly absent from that context (ungrounded generation, e.g. a
    # confident off-topic reply). Threshold 0.5 tolerates paraphrase while
    # catching blatant fabrication.
    hallucination_regression = (not critical_present) or (groundedness < 0.5)
    ungrounded_tokens = sorted(
        retrieval.tokenize(answer or "")
        - _union_tokens(retrieved_texts)
    )
    return {
        "q": question,
        "expected_chunk_ids": expected_chunk_ids,
        "retrieved_chunk_ids": retrieved_ids,
        "groundedness": round(groundedness, 3),
        "tone": tone,
        "critical_fact_present": critical_present,
        "ungrounded_tokens": ungrounded_tokens,
        "hallucination_regression": hallucination_regression,
        "error": error,
    }


def _judge_keywords(
    question: str,
    answer: str,
    expected_keywords: List[str],
    expected_any: List[str],
    tone: Dict[str, Any],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Judge a live answer by required-keyword presence.

    Args:
        question: The factual question asked.
        answer: The live endpoint reply under judgment.
        expected_keywords: Keywords that must all appear in the answer.
        expected_any: Alternatives of which at least one must appear.
        tone: Precomputed tone verdict.
        error: Collection error, if the answer never arrived.

    Returns:
        Dict with keyword coverage as groundedness and the regression flag.
    """
    text = (answer or "").lower()
    missing = [k for k in expected_keywords if k.lower() not in text]
    any_ok = not expected_any or any(a.lower() in text for a in expected_any)
    if expected_any and not any_ok:
        missing = missing + ["any-of:" + "|".join(expected_any)]
    requirements = len(expected_keywords) + (1 if expected_any else 0)
    satisfied = (len(expected_keywords) - len(
        [k for k in expected_keywords if k.lower() not in text]
    )) + (1 if expected_any and any_ok else 0)
    groundedness = (satisfied / requirements) if requirements else 1.0
    hallucination_regression = bool(missing) or error is not None
    return {
        "q": question,
        "expected_keywords": expected_keywords,
        "expected_any": expected_any,
        "groundedness": round(groundedness, 3),
        "tone": tone,
        "critical_fact_present": not missing and error is None,
        "ungrounded_tokens": missing,
        "hallucination_regression": hallucination_regression,
        "error": error,
    }


def collect_live(
    base_url: str, timeout: int = 180, pause_s: float = 12.0,
    resume_from: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Query the live backend for every generation golden question.

    Args:
        base_url: Backend origin, e.g. ``http://127.0.0.1:8000``.
        timeout: Per-request seconds; live LLM replies are slow.
        pause_s: Seconds to wait between requests so rapid-fire collection
            does not burn the model API quota (429s).
        resume_from: Previously collected rows (e.g. from ``--collect-out``);
            questions with a non-empty answer and no error are reused
            instead of re-queried.

    Returns:
        Rows ready for the keyword verdict, with ``error`` set on rows
        whose request failed (they judge as regressions so outages
        surface instead of passing silently).
    """
    golden = load_generation()
    prior = {
        r.get("q", ""): r
        for r in (resume_from or [])
        if r.get("answer") and not r.get("error")
    }
    rows = []
    first = True
    for case in golden:
        if case["q"] in prior:
            prev = prior[case["q"]]
            rows.append(
                {
                    "question": case["q"],
                    "answer": prev.get("answer", ""),
                    "expected_keywords": case.get("expected_keywords", []),
                    "expected_any": case.get("expected_any", []),
                    "error": None,
                }
            )
            continue
        if not first and pause_s > 0:
            time.sleep(pause_s)
        first = False
        answer: str = ""
        error: Optional[str] = None
        try:
            body = json.dumps({"query": case["q"]}).encode("utf-8")
            req = urllib.request.Request(
                base_url.rstrip("/") + "/query-resume/",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw.strip() else None
            except ValueError as exc:
                error = "invalid JSON reply: %s" % exc
                payload = None
            if isinstance(payload, dict):
                answer = str(payload.get("message") or payload.get("answer") or "")
            if not answer and error is None:
                error = "empty live reply: %s" % raw[:200]
        except (urllib.error.URLError, OSError, ValueError) as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
        rows.append(
            {
                "question": case["q"],
                "answer": answer,
                "expected_keywords": case.get("expected_keywords", []),
                "expected_any": case.get("expected_any", []),
                "error": error,
            }
        )
    return rows


def _union_tokens(texts: List[str]) -> set:
    """Union the content-word tokens of several chunk texts."""
    tokens: set = set()
    for text in texts:
        tokens |= retrieval.tokenize(text)
    return tokens


def resolve_answers(
    golden: List[Dict[str, Any]],
    external: Optional[List[Dict[str, Any]]],
    k: int,
) -> List[Dict[str, Any]]:
    """Resolve the (question, answer, context) rows to judge.

    Args:
        golden: Golden retrieval cases.
        external: Optional human-captured live answers; None for stub mode.
        k: Retrieval depth used in stub mode.

    Returns:
        List of rows with q/answer/expected/retrieved fields.
    """
    if external is None:
        rows = []
        for case in golden:
            stub = build_stub_answer(case["q"], k=k)
            rows.append(
                {
                    "question": case["q"],
                    "answer": stub["answer"],
                    "expected_chunk_ids": case["expected_chunk_ids"],
                    "retrieved_ids": stub["retrieved_chunk_ids"],
                    "retrieved_texts": stub["retrieved_texts"],
                }
            )
        return rows
    by_question = {c["q"]: c["expected_chunk_ids"] for c in golden}
    try:
        generation = {c["q"]: c for c in load_generation()}
    except (OSError, ValueError):
        generation = {}
    rows = []
    for entry in external:
        question = entry.get("q", "")
        expected = entry.get("expected_chunk_ids") or by_question.get(question, [])
        gen = generation.get(question, {})
        retrieved_ids = retrieval.retrieve(question, k=k)
        rows.append(
            {
                "question": question,
                "answer": entry.get("answer", ""),
                "expected_chunk_ids": expected,
                "retrieved_ids": retrieved_ids,
                "retrieved_texts": [retrieval.CHUNKS[c] for c in retrieved_ids],
                "expected_keywords": entry.get("expected_keywords")
                or gen.get("expected_keywords", []),
                "expected_any": entry.get("expected_any") or gen.get("expected_any", []),
                "error": entry.get("error"),
            }
        )
    return rows


def run_eval(
    external: Optional[List[Dict[str, Any]]] = None,
    k: int = 3,
    strict: bool = False,
    mode: str = "stub",
) -> Dict[str, Any]:
    """Run the Tier 3 judge over the golden question set.

    Args:
        external: Optional live answers to judge instead of stub answers.
        k: Retrieval depth for grounding context.
        strict: Fail on any hallucination regression or tone failure.
        mode: Label for the run (``stub``, ``external`` or ``live-collected``).

    Returns:
        Summary dict with per-case verdicts and aggregate scores.
    """
    golden = load_golden()
    rows = resolve_answers(golden, external, k)
    cases = [judge_case(**row) for row in rows]
    regressions = [c for c in cases if c["hallucination_regression"]]
    tone_failures = [c for c in cases if not c["tone"]["pass"]]
    avg_groundedness = (
        sum(c["groundedness"] for c in cases) / len(cases) if cases else 1.0
    )
    if external is None:
        passed = not regressions if strict else True
    else:
        passed = not regressions and not tone_failures if strict else not regressions
    return {
        "mode": mode if external is not None else "stub",
        "num_cases": len(cases),
        "avg_groundedness": round(avg_groundedness, 3),
        "hallucination_regressions": len(regressions),
        "tone_failures": len(tone_failures),
        "passed": passed,
        "cases": cases,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for the manual Tier 3 judge.

    Args:
        argv: CLI args (defaults to sys.argv).

    Returns:
        Process exit code (0 pass, 1 fail, 2 usage error).
    """
    parser = argparse.ArgumentParser(
        description="Manual-only Tier 3 generation eval (never a per-change gate)."
    )
    parser.add_argument(
        "--answers",
        default=None,
        help="JSON file of live answers to judge instead of stub answers.",
    )
    parser.add_argument(
        "--collect",
        default=None,
        metavar="BASE_URL",
        help="Query a running backend (e.g. http://127.0.0.1:8000) for every "
        "generation golden question and judge the live replies.",
    )
    parser.add_argument(
        "--collect-out",
        default=None,
        help="Save collected live answers JSON here for audit/human review.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-request seconds for --collect (default 180).",
    )
    parser.add_argument(
        "--pause-secs",
        type=float,
        default=12.0,
        help="Pause between --collect requests to spare the API quota.",
    )
    parser.add_argument("--k", type=int, default=3, help="Retrieval depth (default 3).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any hallucination regression or tone failure.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Write the full verdict JSON to this path.",
    )
    args = parser.parse_args(argv)

    if args.k <= 0:
        print("error: --k must be positive", file=sys.stderr)
        return 2

    if args.answers and args.collect:
        print("error: --answers and --collect are mutually exclusive", file=sys.stderr)
        return 2

    external = None
    mode = "stub"
    if args.answers:
        try:
            with open(args.answers, "r", encoding="utf-8") as fh:
                external = json.load(fh)
        except (OSError, ValueError) as exc:
            print("error: cannot load --answers file: %s" % exc, file=sys.stderr)
            return 2
        mode = "external"
    elif args.collect:
        print("collecting live answers from %s ..." % args.collect)
        resume_from = None
        if args.collect_out:
            try:
                with open(args.collect_out, "r", encoding="utf-8") as fh:
                    resume_from = json.load(fh)
                print("resuming: reusing %d answered row(s) from %s"
                      % (len(resume_from), args.collect_out))
            except (OSError, ValueError):
                resume_from = None
        collected = collect_live(
            args.collect, timeout=args.timeout, pause_s=args.pause_secs,
            resume_from=resume_from,
        )
        if args.collect_out:
            try:
                with open(args.collect_out, "w", encoding="utf-8") as fh:
                    json.dump(
                        [
                            {
                                "q": r["question"],
                                "answer": r["answer"],
                                "expected_keywords": r["expected_keywords"],
                                "expected_any": r["expected_any"],
                                "error": r["error"],
                            }
                            for r in collected
                        ],
                        fh,
                        indent=2,
                    )
            except OSError as exc:
                print("error: cannot write --collect-out: %s" % exc, file=sys.stderr)
                return 2
        external = [
            {
                "q": r["question"],
                "answer": r["answer"],
                "expected_keywords": r["expected_keywords"],
                "expected_any": r["expected_any"],
                "error": r["error"],
            }
            for r in collected
        ]
        mode = "live-collected"

    summary = run_eval(external=external, k=args.k, strict=args.strict, mode=mode)

    print(
        "Tier 3 judge (%s mode): %d cases, avg groundedness %.3f, "
        "%d hallucination regression(s), %d tone failure(s) -> %s"
        % (
            summary["mode"],
            summary["num_cases"],
            summary["avg_groundedness"],
            summary["hallucination_regressions"],
            summary["tone_failures"],
            "PASS" if summary["passed"] else "FAIL",
        )
    )
    for case in summary["cases"]:
        if case["hallucination_regression"] or not case["tone"]["pass"]:
            print(
                "  FLAG %r grounded=%.3f critical_present=%s tone_pass=%s ungrounded=%s%s"
                % (
                    case["q"][:80],
                    case["groundedness"],
                    case["critical_fact_present"],
                    case["tone"]["pass"],
                    ",".join(case["ungrounded_tokens"][:8]),
                    (" error=%s" % case["error"]) if case.get("error") else "",
                )
            )

    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2)
        except OSError as exc:
            print("error: cannot write --json-out: %s" % exc, file=sys.stderr)
            return 2

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
