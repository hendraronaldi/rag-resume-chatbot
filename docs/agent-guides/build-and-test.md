# Build and Test

## Build Commands

### Python Dependencies

```bash
pip install -r requirements.txt
```

Installs all pinned dependencies from `requirements.txt`.

**Known Issues:**
- Python 3.9+ required (Dockerfile uses 3.9.19-slim)
- Some packages require build tools (`gcc`, `python3-dev` on Debian/Ubuntu)

### Docker Build

```bash
docker build -t rag-resume-chatbot .
```

Builds the Docker image using the `Dockerfile`.

**Build Context:** Root directory
**Target:** Python 3.9.19-slim base image

### Google Cloud Build

```bash
gcloud builds submit --region=us-central1 --config cloudbuild.yaml
```

Deploys to Google Cloud Run.

---

## Run Commands

### Development

```bash
uvicorn main:app --reload
```

Starts FastAPI dev server with auto-reload.
- **URL:** http://127.0.0.1:8000
- **Hot reload:** Enabled

### Production

```bash
gunicorn --bind 0.0.0.0:$PORT --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker main:app
```

**Environment Variables:**
- `PORT` - Server port (default: 8000)
- `WORKERS` - Number of worker processes

### Docker Run

```bash
docker run -p 8000:8000 --env-file .env rag-resume-chatbot
```

Runs container with environment variables from `.env` file.

---

## Index Building

### Build Vector Index

```bash
python app/rag/builder.py
```

or

```bash
python builder.py
```

Creates vector index from `app/data/resume.md`.

**Output:** `app/data/index/` directory with:
- `default__vector_store.json`
- `docstore.json`
- `graph_store.json`
- `image__vector_store.json`
- `index_store.json`

**Known Failure Modes:**
- Missing `GOOGLE_API_KEY` - API key required for embeddings
- Missing `app/data/resume.md` - Source file must exist
- Embedding dimension mismatch - Changing `EMBEDDING_DIMENSIONS` requires rebuild

---

## Testing

### Current Status

**No test suite exists yet.** See [AGENTS.md](AGENTS.md) for recommended setup.

### Recommended Setup (When Adding Tests)

#### Run All Tests

```bash
pytest
```

#### Run Single Test

```bash
pytest tests/test_file.py::test_function_name
pytest -k "test_function_name"
```

#### Run with Coverage

```bash
pytest --cov=app --cov-report=html
```

### Test Structure (Recommended)

```
tests/
├── __init__.py
├── test_agent.py      # ResumeRAGAgent tests
├── test_config.py     # Settings tests
├── test_api.py        # FastAPI endpoint tests
└── conftest.py        # Shared fixtures
```

---

## Linting & Formatting

### Current Status

**No linting/formatting tools configured.** See [AGENTS.md](AGENTS.md) for recommended setup.

### Recommended Tools

#### Ruff (Recommended)

```bash
# Check
ruff check .

# Format
ruff format .
```

#### Flake8 + Black

```bash
flake8 .
black .
```

#### Type Checking

```bash
mypy app/
```

---

## CI/CD

### Google Cloud Build

**Trigger:** Manual via `gcloud builds submit`

**Steps:**
1. Build Docker image
2. Push to Google Cloud Run registry

**Region:** us-central1 (required for VertexAI RAG)

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `pip install -r requirements.txt` | Install dependencies |
| `python builder.py` | Build vector index |
| `uvicorn main:app --reload` | Run dev server |
| `docker build -t rag-resume-chatbot .` | Build Docker image |
| `docker run -p 8000:8000 --env-file .env rag-resume-chatbot` | Run container |
| `gcloud builds submit --region=us-central1 --config cloudbuild.yaml` | Deploy to Cloud Run |

---

## Prerequisites Checklist

Before running the application:

- [ ] Python 3.9+ installed
- [ ] `GOOGLE_API_KEY` set in environment
- [ ] Vector index built (`python builder.py`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created (or environment variables exported)
