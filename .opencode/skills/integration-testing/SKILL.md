---
name: integration-testing
description: Write integration tests for this project. Covers test isolation, mocking strategies, and test database setup.
license: MIT
compatibility: Requires pytest, pytest-asyncio, and httpx.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

Integration tests verify that components work together correctly. This project currently uses file-based storage (LlamaIndex), but the patterns below adapt when a database is added.

---

## Adding Required Packages

If not already installed:
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

---

## Test File Location

```
project/
├── app/
│   ├── agent.py
│   └── config.py
├── tests/
│   ├── __init__.py
│   ├── unit/                  # Unit tests
│   │   ├── test_agent.py
│   │   └── test_config.py
│   ├── integration/           # Integration tests
│   │   ├── __init__.py
│   │   ├── test_api.py
│   │   └── test_rag_pipeline.py
│   ├── conftest.py            # Shared fixtures
│   └── fixtures/              # Test data files
│       ├── resume.md
│       └── sample_index/
├── main.py
└── requirements.txt
```

---

## Isolated Test Setup

### Test Database Setup (for future DB)

When a database is added, use **test containers** or **in-memory databases**:
```python
# tests/conftest.py
import pytest
import os

@pytest.fixture(scope="session")
def test_db_url():
    """Use test database URL or in-memory DB for tests."""
    return os.getenv("TEST_DATABASE_URL", "sqlite:///./test.db")

@pytest.fixture(scope="function")
def test_db(test_db_url):
    """Create fresh database for each test."""
    from app.database import init_db, get_db
    
    init_db(test_db_url)
    db = get_db(test_db_url)
    yield db
    # Teardown: clean up test data
    db.close()
    if os.path.exists("test.db"):
        os.remove("test.db")
```

### File-based test setup (current)
```python
@pytest.fixture(scope="function")
def test_index_dir(tmp_path):
    """Create isolated index directory for testing."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    yield str(index_dir)
    # Cleanup automatic with tmp_path

@pytest.fixture(scope="function")
def test_resume_file(tmp_path):
    """Create test resume file."""
    resume_file = tmp_path / "resume.md"
    resume_content = """# John Doe
## Experience
- Senior Python Developer at Tech Corp (2020-Present)
- Backend Engineer at Startup Inc (2018-2020)

## Skills
- Python, FastAPI, PostgreSQL
"""
    resume_file.write_text(resume_content)
    return str(resume_file)
```

---

## Mocking Strategy: What to Mock vs Real

### ALWAYS Mock
- **External API calls**: Google Gemini API, OpenAI API
- **File system in unit tests**: Index file I/O
- **Environment variables**: API keys, paths

### Use Real (when safe)
- **API endpoint testing**: Use TestClient
- **Request/response parsing**: Pydantic models
- **Internal business logic**: When not dependent on external services

### Example: Mixed approach
```python
# tests/integration/test_rag_pipeline.py
from unittest.mock import patch, Mock
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_query_resume_endpoint():
    """Test API endpoint with mocked LLM but real FastAPI."""
    
    # Mock the external LLM API call
    with patch('app.agent.Gemini') as mock_gemini:
        mock_gemini.return_value = Mock(
            complete=Mock(return_value=Mock(text="Mocked resume response"))
        )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/query-resume/",
                json={"query": "What is the candidate's experience?"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["query"] == "What is the candidate's experience?"
```

---

## Test Database Setup/Teardown

### For future PostgreSQL/SQLAlchemy
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="session")
def engine():
    """Create test engine."""
    engine = create_engine("sqlite:///:memory:")
    from app.models import Base
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(engine):
    """Create fresh session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

### Cleanup patterns
```python
@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Ensure test files are cleaned up after each test."""
    yield
    import glob
    for f in glob.glob("./test_*.db"):
        os.remove(f)
```

---

## Running Integration Tests Only

### Run all integration tests
```bash
pytest tests/integration/
```

### Run only integration tests (exclude unit)
```bash
pytest --ignore=tests/unit/
```

### Run tests with specific marker
```bash
# Add to integration test files
import pytest

@pytest.mark.integration
def test_api_flow():
    ...

# Run marked tests
pytest -m integration
```

### Run API tests only
```bash
pytest tests/integration/test_api.py -v
```

---

## API Integration Testing Patterns

### Using FastAPI TestClient (sync)
```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

### Using httpx AsyncClient (async)
```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_query_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/query-resume/",
            json={"query": "Test query"}
        )
    assert response.status_code in [200, 500]  # May fail without index
```

---

## Testing Error Handling

```python
@pytest.mark.asyncio
async def test_invalid_request():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Missing required field
        response = await client.post(
            "/query-resume/",
            json={}
        )
    assert response.status_code == 422  # Validation error
```

---

## Best Practices

1. **Isolation**: Each test should be independent
2. **Fixtures**: Use fixtures for common setup
3. **Descriptive names**: `test_api_returns_422_for_invalid_input`
4. **Assert meaningful things**: Don't just check status codes
5. **Clean up**: Remove test files/artifacts after tests
6. **Use markers**: Mark integration vs unit tests for selective running

---

## Example: Complete Integration Test

```python
# tests/integration/test_api.py
import pytest
from unittest.mock import patch, Mock
from httpx import AsyncClient
from main import app

@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_resume_with_mocked_llm(test_resume_file, test_index_dir):
    """Test the full query-resume endpoint with mocked LLM."""
    
    with patch('app.config.Settings') as mock_settings:
        mock_settings.return_value.RESUME_PATH = test_resume_file
        mock_settings.return_value.INDEX_PATH = test_index_dir
        mock_settings.return_value.LLM = "test-model"
        mock_settings.return_value.GOOGLE_API_KEY = "test-key"
        
        with patch('app.agent.Gemini') as mock_gemini:
            mock_gemini.return_value.complete.return_value.text = "Test response"
            
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/query-resume/",
                    json={"query": "What is the experience?"}
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "What is the experience?"
            assert "message" in data
```

(End of file - total 274 lines)
