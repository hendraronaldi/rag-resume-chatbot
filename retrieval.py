"""Deterministic top-k chunk lookup over a compiled TF-IDF index (guide 03, Tier 2).

No embeddings, no LLM, no third-party deps, no network: stdlib only.

Public contract (frozen):
    retrieve(query: str, k: int = 3) -> List[str]  # chunk IDs, best-first
    tokenize(text: str) -> set                     # word-set tokenizer
    CHUNKS: Dict[str, str]                         # chunk corpus (source of truth)

How it works:
  - `build_index.py` compiles CHUNKS into `index.json` (document frequencies,
    smoothed IDF weights, per-chunk TF-IDF vectors). The artifact is baked at
    build time (guide 01: index baked at Docker compile time).
  - At runtime this module loads `index.json` once at import and ranks chunks
    by TF-IDF dot-product score, tie-broken by chunk id ascending
    (fully deterministic: no randomness, no time-dependence).
  - If the artifact is missing or corrupt, ranking falls back to compiling the
    index inline from CHUNKS, so the module never crashes on import.

Regeneration:
    python3 rag-resume-chatbot/build_index.py
"""

import json
import math
import os
import re
from typing import Any, Dict, List, Set

_WORD = re.compile(r"[a-z0-9+]+")

STOPWORDS = frozenset(
    "what which who whom whose when where why how is are was were be been being "
    "do does did done have has had having a an the and or but of on in to for "
    "with from by at as it its this that these those there their them they you "
    "your we our i me my me tell show list give describe explain compare many "
    "much more most does about into over after".split()
)

CHUNKS = {
    "c01": "Elena maintains the payments ledger service handling idempotent charge capture and refund reconciliation.",
    "c02": "The vector index rebuilds nightly from markdown sources using overlapping windows of eight hundred tokens.",
    "c03": "Staleness mitigation injects the index build date into the system prompt for every request.",
    "c04": "The proxy enforces API keys and per-key rate limits before forwarding traffic upstream.",
    "c05": "Lead capture extracts name and email entities then performs a hardcoded control-plane insert.",
    "c06": "Circuit breakers cap harness loops at five steps with stagnation hashing and an eight second budget.",
    "c07": "Context budget priority keeps system prompt first then chunks then history with FIFO eviction.",
    "c08": "Retrieval evaluation measures hit rate at three against twenty golden factual questions.",
    "c09": "Router evaluation demands one hundred percent accuracy on thirty golden intent queries.",
    "c10": "Generation evaluation uses judge scoring for groundedness and professional tone on master branch.",
    "c11": "Observability opens one trace per request with child spans for router retrieval and generation.",
    "c12": "Feedback ratchet tags traces with votes then locks ideal responses into golden sets.",
    "c13": "Reindex automation fires repository dispatch webhooks from frontend merges to backend rebuilds.",
    "c14": "Tool sandbox restricts models to JSON arguments while credentials hold insert-only privileges.",
    "c15": "The chat node bypasses retrieval and answers from history plus system prompt alone.",
    "c16": "The rag node appends retrieved chunks under the context budget before generating.",
    "c17": "Rate limiting rejects abusive callers with four twenty nine status codes.",
    "c18": "Oversize payloads are rejected at the proxy before reaching language model inference.",
    "c19": "Session state including chat history lives in the Firebase frontend client.",
    "c20": "Docker image compile time bakes the vector index into the backend container.",
}

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.json")


def tokenize(text: str) -> Set[str]:
    return set(_WORD.findall(text.lower())) - STOPWORDS


def _term_counts(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for tok in _WORD.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        counts[tok] = counts.get(tok, 0) + 1
    return counts


def _compile_index(chunks: Dict[str, str]) -> Dict[str, Any]:
    """Compile the chunk corpus into a TF-IDF index artifact (deterministic)."""
    doc_ids = sorted(chunks)
    n = len(doc_ids)
    term_counts = {cid: _term_counts(chunks[cid]) for cid in doc_ids}
    df: Dict[str, int] = {}
    for counts in term_counts.values():
        for term in counts:
            df[term] = df.get(term, 0) + 1
    # Smoothed IDF, always positive and deterministic.
    idf = {term: math.log((n + 1) / (freq + 1)) + 1.0 for term, freq in df.items()}
    doc_vectors = {}
    for cid in doc_ids:
        vec = {
            term: (1.0 + math.log(tf)) * idf[term]
            for term, tf in term_counts[cid].items()
        }
        doc_vectors[cid] = vec
    return {
        "version": 1,
        "built_from": "retrieval.CHUNKS",
        "num_chunks": n,
        "doc_ids": doc_ids,
        "idf": idf,
        "doc_vectors": doc_vectors,
    }


def _load_index() -> Dict[str, Any]:
    """Load the compiled artifact; fall back to an inline compile if needed."""
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        if (
            not isinstance(artifact, dict)
            or artifact.get("version") != 1
            or not isinstance(artifact.get("doc_vectors"), dict)
            or not isinstance(artifact.get("idf"), dict)
            or not isinstance(artifact.get("doc_ids"), list)
        ):
            raise ValueError("malformed index artifact")
        if set(artifact["doc_ids"]) != set(CHUNKS):
            raise ValueError("index artifact out of sync with CHUNKS")
        return artifact
    except (OSError, ValueError, KeyError):
        return _compile_index(CHUNKS)


_INDEX = _load_index()


def retrieve(query: str, k: int = 3) -> List[str]:
    if k <= 0:
        return []
    q_counts = _term_counts(query or "")
    idf = _INDEX["idf"]
    doc_vectors = _INDEX["doc_vectors"]
    q_vec = {
        term: (1.0 + math.log(tf)) * idf[term]
        for term, tf in q_counts.items()
        if term in idf
    }
    scored = []
    for cid in _INDEX["doc_ids"]:
        vec = doc_vectors[cid]
        score = sum(q_vec[t] * vec[t] for t in q_vec if t in vec)
        scored.append((score, cid))
    # Deterministic ranking: best score first, ties broken by chunk id ascending.
    # An empty/blank query scores 0 everywhere -> deterministic top-k by id.
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [cid for _, cid in scored[:k]]
