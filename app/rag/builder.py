import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.embeddings.google import GeminiEmbedding
from llama_index.core.storage.storage_context import StorageContext
from app.config import get_settings

def build_and_persist_index():
    settings = get_settings()

    """
    Build vector store index from resume and persist it to disk
    """
    # Ensure storage directory exists
    storage_dir = settings.INDEX_PATH
    os.makedirs(storage_dir, exist_ok=True)

    # Initialize Gemini Embedding
    embedding = GeminiEmbedding(
        model=settings.EMBEDDING_MODEL, 
        api_key=settings.GEMINI_API_KEY
    )

    # Load resume document
    documents = SimpleDirectoryReader(input_files=[settings.RESUME_PATH]).load_data()

    # Create storage context
    storage_context = StorageContext.from_defaults()

    # Create vector index and persist
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context,
        embed_model=embedding
    )

    # Explicitly persist the index
    index.storage_context.persist(persist_dir=storage_dir)

    print(f"Vector index successfully built and persisted to {storage_dir}")

if __name__ == "__main__":
    build_and_persist_index()