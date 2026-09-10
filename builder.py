import json
import os
from datetime import date, datetime, timezone

from google.genai import types
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

from app.config import get_settings


_BUILD_DATE_FILENAME = "build_date.json"


def _is_valid_date(value: object) -> bool:
    """True when value is a parseable ISO-8601 calendar date. Never raises.

    Args:
        value: Candidate date value of unknown shape.

    Returns:
        True only for non-blank ISO-8601 calendar-date strings.
    """
    try:
        if not isinstance(value, str) or not value.strip():
            return False
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _build_date_artifact(source_path: str) -> dict[str, str]:
    """Create deterministic metadata for the persisted vector index.

    Args:
        source_path: Single resume source the index was built from.

    Returns:
        Mapping with the UTC build date and the normalized source label.
    """
    return {
        "build_date": datetime.now(timezone.utc).date().isoformat(),
        "source": source_path.lstrip("./").replace(os.sep, "/"),
    }


def _write_build_date_artifact(storage_dir: str, source_path: str) -> None:
    """Write byte-stable build-date metadata next to persisted index files.

    Args:
        storage_dir: Persisted index directory receiving build_date.json.
        source_path: Single resume source the index was built from.
    """
    artifact_path = os.path.join(storage_dir, _BUILD_DATE_FILENAME)
    payload = json.dumps(
        _build_date_artifact(source_path), sort_keys=True, separators=(",", ": ")
    )
    with open(artifact_path, "w", encoding="utf-8") as fh:
        fh.write(payload + "\n")


def build_and_persist_index() -> None:
    """Build and persist the vector index from the resume source.

    The LlamaIndex vector-store files are written unchanged to
    ``app/data/index/``. A deterministic ``build_date.json`` artifact is also
    written in that persisted index directory with ``build_date`` as the
    current UTC calendar date and ``source`` as ``app/data/resume.md``.

    Raises:
        FileNotFoundError: If the configured resume source file is missing.
    """
    settings = get_settings()
    storage_dir = settings.INDEX_PATH
    resume_path = settings.RESUME_PATH

    if not os.path.isfile(resume_path):
        message = (
            f"Resume source file not found: {resume_path}. "
            "Cannot build vector index from an empty source."
        )
        raise FileNotFoundError(message)

    # Ensure storage directory exists
    os.makedirs(storage_dir, exist_ok=True)

    # Initialize Gemini Embedding
    embedding = GoogleGenAIEmbedding(
        model_name=settings.EMBEDDING_MODEL,
        api_key=settings.GOOGLE_API_KEY,
        embedding_config=types.EmbedContentConfig(
            outputDimensionality=settings.EMBEDDING_DIMENSIONS
        ),
    )

    # Load resume document
    documents = SimpleDirectoryReader(input_files=[resume_path]).load_data()

    # Create storage context
    storage_context = StorageContext.from_defaults()

    # Create vector index and persist
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embedding,
    )

    # Explicitly persist the index
    index.storage_context.persist(persist_dir=storage_dir)
    _write_build_date_artifact(storage_dir, resume_path)

    print(f"Vector index successfully built and persisted to {storage_dir}")


if __name__ == "__main__":
    build_and_persist_index()
