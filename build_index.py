"""Build step for the compiled retrieval index.

Regenerates `index.json` from the chunk corpus (`retrieval.CHUNKS`):

    python3 rag-resume-chatbot/build_index.py

Run from the repo root (or anywhere; paths resolve relative to this file).
Deterministic: same corpus always yields a byte-identical artifact modulo
JSON key order, which is fixed via sort_keys=True. Stdlib only.

The index build date (consumed by `staleness` for prompt injection and
post-date refusal) is baked into the artifact as `build_date`: it defaults
to `staleness.INDEX_BUILD_DATE`, and a Docker build-time override can be
injected via the PORTFOLIO_INDEX_BUILD_DATE environment variable (must be
a valid ISO-8601 calendar date, otherwise the default wins).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import retrieval
import staleness

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.json")


def _resolve_build_date() -> str:
    """Build date to bake: env override wins when valid, else the default."""
    try:
        override = os.environ.get("PORTFOLIO_INDEX_BUILD_DATE", "")
        if isinstance(override, str) and override.strip():
            date.fromisoformat(override.strip())
            return override.strip()
    except (ValueError, TypeError):
        pass
    return staleness.INDEX_BUILD_DATE


def main() -> None:
    artifact = retrieval._compile_index(retrieval.CHUNKS)
    artifact["build_date"] = _resolve_build_date()
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {OUTPUT} ({artifact['num_chunks']} chunks)")


if __name__ == "__main__":
    main()
