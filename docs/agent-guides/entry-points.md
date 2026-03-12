# Entry Points

## API Endpoints (Web)

All endpoints served by FastAPI on `http://127.0.0.1:8000` (development) or configured port (production).

### Query Domain

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/query-resume/` | POST | `main.py:51` | Query resume using natural language |
| `/feedback/` | POST | `main.py:76` | Receive feedback payload |

### Health/Monitoring

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/` | GET | `main.py:89` | Health check endpoint |

### Request/Response Models

```python
class QueryRequest(BaseModel):
    query: str

# Response: { "query": "...", "message": "..." }
```

## CLI Commands

### Index Management

| Command | Module | Purpose |
|---------|--------|---------|
| `python builder.py` | `builder.py:45` | Build and persist vector index from resume.md |

### Application Startup

| Command | Module | Purpose |
|---------|--------|---------|
| `uvicorn main:app --reload` | `main.py:93` | Run development server |
| `gunicorn --bind 0.0.0.0:$PORT --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker main:app` | `Dockerfile` | Run production server |

## Python Module Exports

### app.config

```python
class Settings:
    GOOGLE_API_KEY: Optional[str]
    LLM: str = 'gemini-2.5-flash'
    EMBEDDING_MODEL: str = 'gemini-embedding-001'
    EMBEDDING_DIMENSIONS: int = 768
    INDEX_PATH: str = './app/data/index'
    RESUME_PATH: str = './app/data/resume.md'

def get_settings() -> Settings
```

### app.agent

```python
class ResumeRAGAgent:
    def __init__(self, settings: Settings)
    def query_resume(self, query: str) -> str
```

## Shell Scripts (.specify)

| Script | Purpose |
|--------|---------|
| `.specify/scripts/bash/check-prerequisites.sh` | Validate feature branch prerequisites |
| `.specify/scripts/bash/create-new-feature.sh` | Create new feature branch |
| `.specify/scripts/bash/setup-plan.sh` | Setup planning context |
| `.specify/scripts/bash/update-agent-context.sh` | Update agent context |
| `.specify/scripts/bash/common.sh` | Shared shell utilities |

## Docker

| Entry Point | Command |
|-------------|---------|
| Container startup | `gunicorn --bind 0.0.0.0:$PORT --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker main:app` |
| Port | `8000` (configurable via `PORT` env var) |
| Workers | Configurable via `WORKERS` env var |
