import json
import sys
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest

import staleness


def _ensure_module(name: str) -> ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return module


def _stub_heavy_imports() -> None:
    google_mod = _ensure_module("google")
    genai_mod = _ensure_module("google.genai")
    genai_types_mod = _ensure_module("google.genai.types")
    if not hasattr(genai_types_mod, "EmbedContentConfig"):
        setattr(genai_types_mod, "EmbedContentConfig", lambda **kwargs: object())
    setattr(genai_mod, "types", genai_types_mod)
    setattr(google_mod, "genai", genai_mod)

    _ensure_module("llama_index")
    core_mod = _ensure_module("llama_index.core")
    if not hasattr(core_mod, "SimpleDirectoryReader"):
        setattr(core_mod, "SimpleDirectoryReader", object)
    if not hasattr(core_mod, "VectorStoreIndex"):
        setattr(core_mod, "VectorStoreIndex", object)
    storage_mod = _ensure_module("llama_index.core.storage")
    context_mod = _ensure_module("llama_index.core.storage.storage_context")
    if not hasattr(context_mod, "StorageContext"):
        setattr(context_mod, "StorageContext", object)
    setattr(storage_mod, "storage_context", context_mod)
    setattr(core_mod, "storage_context", storage_mod)
    embeddings_mod = _ensure_module("llama_index.embeddings")
    google_genai_mod = _ensure_module("llama_index.embeddings.google_genai")
    if not hasattr(google_genai_mod, "GoogleGenAIEmbedding"):
        setattr(google_genai_mod, "GoogleGenAIEmbedding", object)
    setattr(embeddings_mod, "google_genai", google_genai_mod)

    pool_mod = _ensure_module("app.model_pool")
    if not hasattr(pool_mod, "ROUTING_MODEL_POOL"):
        pool_mod.ROUTING_MODEL_POOL = (
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
        )
    if not hasattr(pool_mod, "RAG_MODEL_POOL"):
        pool_mod.RAG_MODEL_POOL = (
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        )
    if not hasattr(pool_mod, "CHAT_MODEL_POOL"):
        pool_mod.CHAT_MODEL_POOL = (
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
        )


_STUBBED_MODULES = (
    "google",
    "google.genai",
    "google.genai.types",
    "llama_index",
    "llama_index.core",
    "llama_index.core.storage",
    "llama_index.core.storage.storage_context",
    "llama_index.embeddings",
    "llama_index.embeddings.google_genai",
    "app.model_pool",
)


def _import_builder_with_isolated_stubs():
    """Import builder without leaking synthetic dependency modules globally."""
    missing = object()
    saved_modules = {name: sys.modules.get(name, missing) for name in _STUBBED_MODULES}
    saved_parent_attrs = {}
    for name in _STUBBED_MODULES:
        parent_name, separator, child_name = name.rpartition(".")
        if separator and parent_name in sys.modules:
            parent = sys.modules[parent_name]
            saved_parent_attrs[name] = getattr(parent, child_name, missing)

    try:
        _stub_heavy_imports()
        import builder as imported_builder

        return imported_builder
    finally:
        for name, previous in saved_modules.items():
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        for name, previous in saved_parent_attrs.items():
            parent_name, _, child_name = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is None:
                continue
            if previous is missing:
                if hasattr(parent, child_name):
                    delattr(parent, child_name)
            else:
                setattr(parent, child_name, previous)


# Keep builder's inert import doubles local to this module's import operation.
builder = _import_builder_with_isolated_stubs()


def test_builder_leaves_index_build_date_artifact(tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("resume", encoding="utf-8")
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    builder._write_build_date_artifact(str(index_dir), str(resume))

    artifact = json.loads((index_dir / "build_date.json").read_text(encoding="utf-8"))
    assert set(artifact) == {"build_date", "source"}
    assert date.fromisoformat(artifact["build_date"]).isoformat() == artifact["build_date"]
    assert artifact["source"].endswith("resume.md")


def test_builder_missing_source_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        builder,
        "get_settings",
        lambda: SimpleNamespace(
            INDEX_PATH=str(tmp_path),
            RESUME_PATH=str(tmp_path / "missing.md"),
            EMBEDDING_MODEL="offline-embedding",
            GOOGLE_API_KEY="offline-key",
            EMBEDDING_DIMENSIONS=768,
        ),
    )

    with pytest.raises(FileNotFoundError):
        builder.build_and_persist_index()


def test_resolve_live_index_build_date_prefers_artifact(tmp_path):
    (tmp_path / "build_date.json").write_text(
        '{"build_date": "2026-08-31", "source": "app/data/resume.md"}', encoding="utf-8"
    )

    resolved = staleness.resolve_live_build_date(str(tmp_path))

    assert resolved == "2026-08-31"
    assert "do not have that information yet" in staleness.build_system_prompt(resolved)


def test_resolve_live_index_build_date_falls_back(tmp_path):
    assert staleness.resolve_live_build_date(str(tmp_path)) == staleness._get_build_date()

    (tmp_path / "build_date.json").write_text("not json", encoding="utf-8")

    assert staleness.resolve_live_build_date(str(tmp_path)) == staleness._get_build_date()


def test_system_prompt_contains_index_build_date_and_refusal_phrase():
    prompt = staleness.build_system_prompt("2026-08-31")

    assert "2026-08-31" not in prompt
    assert "do not have that information yet" in prompt
