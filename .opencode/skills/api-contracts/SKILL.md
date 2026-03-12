---
name: api-contracts
description: API design standards for this project. Covers request/response patterns, versioning, error formats, and OpenAPI usage.
license: MIT
compatibility: Built into FastAPI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

This project uses **FastAPI** which provides automatic OpenAPI/Swagger documentation. Follow these standards for consistent API design.

---

## Request/Response Patterns

### Standard Request Model
Use Pydantic `BaseModel` for all request bodies.

```python
from pydantic import BaseModel, Field
from typing import Optional

class QueryRequest(BaseModel):
    query: str = Field(..., description="The natural language query")
    max_results: Optional[int] = Field(5, ge=1, le=20)
```

### Standard Response Model
```python
from pydantic import BaseModel
from typing import Optional, Any

class QueryResponse(BaseModel):
    query: str
    message: str
    sources: Optional[list] = None
```

### Envelope Pattern (optional, for consistency)
```python
class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {"message": "Result here"},
                "error": None
            }
        }
```

---

## Versioning Rules

### URL Path Versioning (Recommended)

Structure: `/api/v{version}/{resource}`

```python
from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")

@v1_router.post("/query-resume/")
async def query_resume(request: QueryRequest):
    ...

# In main.py
app.include_router(v1_router)
```

### Versioning Strategy
1. **Major version** in URL: `/api/v1/`, `/api/v2/`
2. **Deprecation**: Support old versions for at least 3 months
3. **Breaking changes**: Always create new version
4. **Documentation**: Keep docs for all active versions

---

## Error Format Standards

### Use HTTP Status Codes Correctly

| Code | Usage |
|------|-------|
| 200  | Success |
| 201  | Created |
| 400  | Bad Request (invalid input) |
| 401  | Unauthorized |
| 403  | Forbidden |
| 404  | Not Found |
| 422  | Validation Error |
| 429  | Rate Limited |
| 500  | Internal Server Error |

### Error Response Schema
```python
from pydantic import BaseModel
from typing import Optional, List

class ErrorDetail(BaseModel):
    field: str
    message: str

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    fields: Optional[List[ErrorDetail]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Validation Error",
                "detail": "Request validation failed",
                "fields": [
                    {"field": "query", "message": "Field required"}
                ]
            }
        }
```

### Raising Errors in Endpoints
```python
from fastapi import HTTPException

@app.post("/query-resume/")
async def query_resume(request: QueryRequest):
    if not request.query:
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty"
        )
    
    try:
        result = rag_agent.query_resume(request.query)
        return {"query": request.query, "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## OpenAPI/Swagger Usage

FastAPI automatically generates OpenAPI docs. Configure properly:

### App Configuration
```python
app = FastAPI(
    title="Resume RAG API",
    description="AI-powered API to query personal resume using Persistent RAG",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)
```

### Adding Examples
```python
from pydantic import BaseModel, Field, ConfigDict

class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query about the resume",
        examples=[
            "What is the candidate's Python experience?",
            "List all work experiences"
        ]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "What is the candidate's Python experience?"
            }
        }
    )
```

### Accessing Documentation
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

---

## API Endpoint Patterns

### Naming Conventions
- Use lowercase with hyphens: `/query-resume` NOT `/queryResume`
- Use plural nouns for collections: `/users`, `/feedback`
- Use HTTP methods semantically:
  - `GET` - Retrieve
  - `POST` - Create
  - `PUT` - Update (full)
  - `PATCH` - Update (partial)
  - `DELETE` - Delete

### Example Endpoints
```python
# POST /api/v1/query-resume/
# Query the resume with natural language

# GET /api/v1/health
# Health check endpoint

# POST /api/v1/feedback
# Submit feedback
```

---

## Request Validation

### Using Pydantic Validators
```python
from pydantic import field_validator

class QueryRequest(BaseModel):
    query: str
    
    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Query cannot be empty')
        if len(v) > 1000:
            raise ValueError('Query too long (max 1000 characters)')
        return v.strip()
```

---

## Response Caching

For expensive operations, add caching headers:
```python
from fastapi import Response

@app.get("/api/v1/health")
async def health_check(response: Response):
    response.headers["Cache-Control"] = "no-cache"
    return {"status": "healthy"}
```

---

## Rate Limiting (Future)

When implementing rate limiting:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/query-resume/")
@limiter.limit("10/minute")
async def query_resume(request: Request, query_request: QueryRequest):
    ...
```

---

## Best Practices Summary

1. **Always validate input** with Pydantic
2. **Use proper HTTP status codes**
3. **Provide meaningful error messages**
4. **Document with OpenAPI annotations**
5. **Version APIs in URL path**
6. **Keep responses consistent** (use envelope if doing so)
7. **Add examples** to request/response models
8. **Use async/await** for I/O operations

---

## Example: Complete Endpoint

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(
    title="Resume RAG API",
    version="1.0.0"
)

class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query about the resume",
        min_length=1,
        max_length=1000
    )

class QueryResponse(BaseModel):
    query: str
    message: str
    sources: Optional[list] = None

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None

@app.post(
    "/api/v1/query-resume/",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"}
    }
)
async def query_resume(request: QueryRequest):
    """
    Query the resume using natural language.
    
    Provide a question about the candidate's background,
    skills, or experience and receive a relevant response.
    """
    try:
        response = rag_agent.query_resume(request.query)
        return QueryResponse(
            query=request.query,
            message=response
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
```

(End of file - total 305 lines)
