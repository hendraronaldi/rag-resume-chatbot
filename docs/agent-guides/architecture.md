# Architecture

## System Overview

This is a **Resume RAG (Retrieval Augmented Generation) API** that allows users to query a personal resume using natural language. The system uses AI to understand queries and retrieve relevant information from a vectorized resume index.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI    │────▶│ ResumeRAG   │
│  (Request)  │     │   Server    │     │   Agent     │
└─────────────┘     └─────────────┘     └─────────────┘
                                                │
                    ┌─────────────┐             │
                    │   Gemini    │◀────────────┘
                    │  LLM API   │
                    └─────────────┘
```

## Module Map

| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI application entry point, endpoint definitions, CORS middleware |
| `app/agent.py` | ResumeRAGAgent class - manages LLM, vector index, and query processing |
| `app/config.py` | Settings class - environment configuration (API keys, paths, models) |
| `builder.py` | Index builder - creates and persists vector index from resume.md |

## Data Flow

### Query Flow
1. **Client** sends POST request to `/query-resume/` with JSON body `{ "query": "..." }`
2. **FastAPI** validates request and passes to `ResumeRAGAgent.query_resume()`
3. **ResumeRAGAgent**:
   - Retrieves relevant context from vector index using similarity search
   - Sends query + context to Gemini LLM
   - Returns formatted response
4. **FastAPI** returns JSON response `{ "query": "...", "message": "..." }`

### Index Build Flow
1. Run `python app/rag/builder.py` (or `builder.py`)
2. Loads `app/data/resume.md` using SimpleDirectoryReader
3. Creates vector embeddings using Gemini embedding model
4. Persists vector index to `app/data/index/`

### Data Storage
- **Vector Index**: `./app/data/index/` (JSON files - docstore, graph_store, index_store, vector_store)
- **Resume Source**: `./app/data/resume.md`
- **Environment**: `.env` file with GOOGLE_API_KEY

## External Dependencies

| Dependency | Purpose |
|------------|---------|
| **FastAPI** | Web framework for REST API |
| **LlamaIndex** | RAG framework for indexing and querying |
| **Gemini (Google AI)** | LLM for response generation + embedding model |
| **gunicorn** | Production WSGI server |
| **uvicorn** | Development ASGI server |

### Environment Variables
```
GOOGLE_API_KEY       # Required - Google AI API key
LLM                  # Optional - LLM model (default: gemini-2.5-flash)
EMBEDDING_MODEL      # Optional - Embedding model (default: gemini-embedding-001)
EMBEDDING_DIMENSIONS # Optional - Embedding size (default: 768)
INDEX_PATH           # Optional - Vector index directory (default: ./app/data/index)
RESUME_PATH          # Optional - Resume markdown file (default: ./app/data/resume.md)
```

## Key Design Patterns

### ReAct Agent Pattern
The system uses LlamaIndex's `ReActAgent` for query processing, which combines retrieval with reasoning.

### Persistent Vector Store
- Index is built once and persisted to disk
- Loaded at startup for fast queries
- Uses Gemini embeddings for semantic search

### Chat Memory
- Maintains conversation context using `ChatMemoryBuffer`
- Token limit: 3000 tokens

### Structured Response Format
- Plain Markdown output (no JSON in response body)
- Headers and bullet points for readability
- Direct answers - states when information is not found

## What NOT to Touch and Why

### DO NOT Modify
1. **`app/data/index/`** - Persisted vector store; modifying manually corrupts the index
2. **`app/data/resume.md`** - Source of truth for resume data; edit directly instead
3. **`.env` file** - Contains secrets; use environment variables or .env.development
4. **`requirements.txt`** - Locked versions for reproducibility; update only when needed

### Avoid Without Testing
1. **LLM prompt template** (`app/agent.py:4306-4332`) - Changes affect response quality
2. **Embedding dimensions** - Changing requires rebuilding the entire index
3. **INDEX_PATH / RESUME_PATH** - Requires index rebuild if changed

### Safe to Modify
- API endpoints in `main.py` (add new endpoints)
- FastAPI CORS settings for different origins
- Chat memory token limits for longer conversations

## Technology Stack

- **Python**: 3.9+
- **Web Framework**: FastAPI
- **RAG Framework**: LlamaIndex
- **LLM**: Google Gemini (gemini-2.5-flash)
- **Embedding**: Google Gemini (gemini-embedding-001)
- **Deployment**: Docker, gunicorn
