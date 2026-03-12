# Conventions

## Naming Conventions

### Classes
- **PascalCase** - e.g., `ResumeRAGAgent`, `Settings`, `QueryRequest`
- Descriptive nouns or noun phrases

### Functions/Methods
- **snake_case** - e.g., `get_settings()`, `query_resume()`, `build_and_persist_index()`
- Verb or verb phrases
- Private methods: prefix with underscore `_private_method()`

### Variables
- **snake_case** - e.g., `storage_dir`, `api_key`, `embedding_model`
- Constants: Use descriptive names, value is obvious

### Environment Variables
- **SCREAMING_SNAKE_CASE** - e.g., `GOOGLE_API_KEY`, `EMBEDDING_DIMENSIONS`

## Import Order

Organize imports in three sections:

```python
# 1. Standard library
import os
import json
from typing import Optional

# 2. Third-party
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_index.core import load_index_from_storage

# 3. Local application
from app.agent import ResumeRAGAgent
from app.config import get_settings
```

## Error Handling Patterns

### FastAPI Endpoints
```python
try:
    response = rag_agent.query_resume(request.query)
    return {"query": request.query, "message": response}
except Exception as e:
    if hasattr(e, "response"):
        # Handle specific error types
        if isinstance(e.response, grpc.RpcError):
            if e.response.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise HTTPException(status_code=429, detail=str(e))
    else:
        raise HTTPException(status_code=500, detail=str(e))
```

### Agent/Service Layer
```python
try:
    response = self.agent.chat(query)
    return str(response)
except Exception as e:
    print(f"Error querying resume: {e}")
    raise e
```

### Key Patterns
- Use `try/except` for operations that may fail
- Catch specific exceptions when possible
- Log errors with descriptive messages
- Return appropriate HTTP status codes in API endpoints
- Re-raise exceptions after logging

## Folder Structure

```
rag-resume-chatbot/
├── main.py                    # FastAPI app entry point
├── builder.py                 # Index builder script
├── app/
│   ├── __init__.py
│   ├── agent.py              # ResumeRAGAgent class
│   ├── config.py             # Settings class
│   ├── data/
│   │   ├── index/           # Vector index (persisted)
│   │   └── resume.md        # Resume source file
│   └── rag/
│       └── builder.py        # (alternative location)
├── .env                      # Local secrets (never commit)
└── requirements.txt          # Pinned dependencies
```

## Type Hints

Always use type hints for function signatures:

```python
def query_resume(self, query: str) -> str:
    """Query the resume using an agent-based approach."""
    ...

def get_settings() -> Settings:
    ...
```

Use `Optional[X]` instead of `X | None` for compatibility with older Python versions:

```python
GOOGLE_API_KEY: Optional[str] = os.getenv('GOOGLE_API_KEY')
```

## Pydantic Models

Use Pydantic `BaseModel` for request/response schemas:

```python
class QueryRequest(BaseModel):
    query: str
```

## Configuration

- Use environment variables for sensitive data (API keys, secrets)
- Use `.env` files for local development
- Use Pydantic or dataclasses for configuration management
- Never hardcode secrets in source code

## FastAPI Best Practices

- Use `async/await` for I/O operations
- Add docstrings to all endpoints
- Use appropriate HTTP methods (GET, POST, etc.)
- Return JSON-serializable responses

```python
@app.post("/query-resume/")
async def query_resume(request: QueryRequest):
    """
    Endpoint to query the resume using natural language.
    
    :param request: Query about the resume
    :return: Relevant information from the resume
    """
    ...
```

## Anti-Patterns (Avoid These)

### 1. Hardcoded Paths
```python
# BAD
index = load_index_from_storage(storage_context, embed_model=embedding)

# GOOD - use settings
storage_context = StorageContext.from_defaults(persist_dir=settings.INDEX_PATH)
```

### 2. print() for Logging
```python
# BAD
print(f"Error: {e}")

# GOOD - use proper logging
import logging
logger = logging.getLogger(__name__)
logger.error(f"Error: {e}")
```

### 3. Missing Type Hints
```python
# BAD
def process(query):
    ...

# GOOD
def process(query: str) -> str:
    ...
```

### 4. Checking in Secrets
```python
# BAD - .env contains secrets
GOOGLE_API_KEY=sk-xxx

# GOOD - .gitignore includes .env, use .env.example for template
```

### 5. Swallowing Exceptions
```python
# BAD
try:
    do_something()
except:
    pass

# GOOD
try:
    do_something()
except SpecificException as e:
    logger.error(f"Failed: {e}")
    raise
```

### 6. Not Validating Environment
```python
# BAD - fails silently at runtime
if not os.path.exists(settings.INDEX_PATH):
    print("ERROR: Vector index not found!")
    raise SystemExit(1)
```
This pattern is actually **GOOD** - fail fast with clear error messages.

## Docstrings

Use Google-style docstrings:

```python
def function(param: str) -> bool:
    """Short one-line description.

    Longer description if needed.

    Args:
        param: Description of parameter.

    Returns:
        Description of return value.
    """
```
