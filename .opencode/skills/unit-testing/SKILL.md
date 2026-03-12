---
name: unit-testing
description: Write and run unit tests for this project using pytest. Covers fixtures, mocking, and naming conventions.
license: MIT
compatibility: Requires pytest and pytest-asyncio.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

Unit testing in this project uses **pytest** as the framework.

---

## Adding pytest to the project

If not already installed, add to requirements.txt:
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

Install: `pip install -r requirements.txt`

---

## Test File Location

Place unit tests in `tests/` directory at project root:
```
project/
├── app/
│   ├── agent.py
│   └── config.py
├── tests/
│   ├── __init__.py
│   ├── test_agent.py       # tests for app/agent.py
│   └── test_config.py      # tests for app/config.py
├── main.py
└── requirements.txt
```

---

## Naming Conventions

- Test files: `test_<module_name>.py`
- Test functions: `test_<what_is_tested>`
- Test classes: `Test<WhatIsTested>`
- Fixtures: descriptive names matching what they provide

Examples:
```python
# test_agent.py
def test_query_resume_returns_string():
    ...

class TestResumeRAGAgent:
    def test_agent_initialization(self):
        ...
```

---

## Creating Fixtures

Use `@pytest.fixture` decorator in `tests/conftest.py` or within test files.

### Basic fixture example
```python
# tests/conftest.py
import pytest
from app.config import Settings, get_settings

@pytest.fixture
def mock_settings():
    """Provide test settings with mocked values."""
    settings = Settings()
    settings.GOOGLE_API_KEY = "test-key"
    settings.LLM = "gemini-2.5-flash"
    settings.INDEX_PATH = "./tests/fixtures/index"
    settings.RESUME_PATH = "./tests/fixtures/resume.md"
    return settings

@pytest.fixture
def sample_query():
    """Provide a sample query string."""
    return "What is the candidate's experience with Python?"
```

### Fixture with teardown
```python
@pytest.fixture
def temp_index_dir(tmp_path):
    """Create temporary index directory, cleanup after."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    yield str(index_dir)
    # Cleanup happens automatically with tmp_path
```

---

## Mocking Patterns

### Mocking with unittest.mock
```python
from unittest.mock import Mock, patch, MagicMock

def test_query_resume_with_mocked_agent(mock_settings):
    with patch('app.agent.ResumeRAGAgent') as MockAgent:
        mock_instance = MockAgent.return_value
        mock_instance.query_resume.return_value = "Mocked response"
        
        from app.agent import ResumeRAGAgent
        agent = ResumeRAGAgent(settings=mock_settings)
        result = agent.query_resume("test query")
        
        assert result == "Mocked response"
        mock_instance.query_resume.assert_called_once_with("test query")
```

### Mocking external dependencies
```python
@patch('app.agent.Gemini')
def test_llm_initialization(mock_gemini, mock_settings):
    from app.agent import ResumeRAGAgent
    
    mock_gemini.return_value = Mock()
    agent = ResumeRAGAgent(settings=mock_settings)
    
    mock_gemini.assert_called_once()
```

### Mocking file system
```python
from pathlib import Path
from unittest.mock import patch, mock_open

def test_load_resume(mock_settings):
    resume_content = "# John Doe\n## Experience\n- Python Developer"
    
    with patch('pathlib.Path.exists', return_value=True):
        with patch('pathlib.Path.read_text', return_value=resume_content):
            # Test code here
            ...
```

---

## Running Tests

### Run all tests
```bash
pytest
```

### Run a single test file
```bash
pytest tests/test_agent.py
```

### Run a single test function
```bash
pytest tests/test_agent.py::test_query_resume_returns_string
```

### Run tests matching a pattern
```bash
pytest -k "test_query"
```

### Run with verbose output
```bash
pytest -v
```

### Run with coverage
```bash
pytest --cov=app --cov-report=html
```

### Run tests in a specific directory
```bash
pytest tests/unit/
```

---

## Async Testing

If testing async functions, use `pytest-asyncio`:

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_query():
    await asyncio.sleep(0.1)  # Your async code
    assert True
```

---

## Test Organization Best Practices

1. **Arrange-Act-Assert** pattern in each test
2. One assertion per test when possible
3. Keep tests independent - no shared state
4. Use descriptive test names that explain what is being verified
5. Group related tests in classes

---

## Example: Complete Unit Test

```python
# tests/test_config.py
import pytest
from app.config import Settings, get_settings

class TestSettings:
    def test_default_llm_is_gemini_2_5_flash(self):
        settings = Settings()
        assert settings.LLM == "gemini-2.5-flash"
    
    def test_index_path_default(self):
        settings = Settings()
        assert settings.INDEX_PATH == "./app/data/index"

class TestGetSettings:
    def test_get_settings_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)
```

(End of file - total 181 lines)
