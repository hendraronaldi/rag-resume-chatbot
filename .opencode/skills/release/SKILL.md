---
name: release
description: Release management for this project. Covers tagging, CHANGELOG format, deployment checklist, and smoke testing.
license: MIT
compatibility: Requires git and GitHub CLI (optional).
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

Follow these steps to create a release for this project.

---

## Version Numbering

Use **Semantic Versioning** (SemVer): `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

Examples: `1.0.0`, `1.1.0`, `2.0.0`

---

## Tagging

### Create an annotated tag
```bash
# Tag with version
git tag -a v1.0.0 -m "Release v1.0.0"

# Push tag to remote
git push origin v1.0.0
```

### List tags
```bash
git tag
git tag -l
```

### Delete tag (if needed)
```bash
# Local
git tag -d v1.0.0

# Remote
git push origin --delete v1.0.0
```

---

## CHANGELOG Format

Create or update `CHANGELOG.md` in project root:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2024-01-15

### Added
- New feedback endpoint for user submissions
- Rate limiting support for API endpoints

### Changed
- Updated LlamaIndex to version 0.12.x
- Improved error handling in query-resume endpoint

### Fixed
- Fixed memory leak in RAG agent
- Resolved CORS configuration issue

## [1.0.0] - 2024-01-01

### Added
- Initial release
- Resume RAG API with natural language query support
- Health check endpoint
```

### Generating CHANGELOG from git
```bash
# Using git-chglog (if installed)
git-chglog --next-tag v1.1.0 -o CHANGELOG.md

# Or manually with git log
git log --pretty=format:"%h - %s (%an)" v1.0.0..HEAD
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] All tests pass (`pytest`)
- [ ] Linting passes (`ruff check .`)
- [ ] Type checking passes (`mypy app/`)
- [ ] CHANGELOG updated
- [ ] Version bumped in code (if applicable)
- [ ] No secrets in code
- [ ] Dependencies updated in requirements.txt

### Build
- [ ] Build Docker image (if applicable)
- [ ] Test Docker image locally
- [ ] Push to container registry

### Production Deployment
- [ ] Backup production database
- [ ] Run database migrations (if any)
- [ ] Deploy to production environment
- [ ] Verify environment variables set correctly
- [ ] Check application logs

### Post-Deployment
- [ ] Run smoke tests
- [ ] Verify health endpoint
- [ ] Monitor error rates
- [ ] Check API response times

---

## Build and Push Docker Image

```bash
# Build image
docker build -t rag-resume-chatbot:latest .

# Tag for registry
docker tag rag-resume-chatbot:latest registry.example.com/rag-resume-chatbot:v1.0.0

# Push to registry
docker push registry.example.com/rag-resume-chatbot:v1.0.0
```

---

## Smoke Tests After Deploy

Run these commands to verify the deployment:

### 1. Health Check
```bash
curl -s https://your-api.com/ | jq
# Expected: {"status":"healthy"}
```

### 2. Query Endpoint Test
```bash
curl -s -X POST https://your-api.com/api/v1/query-resume/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the candidate name?"}'
# Expected: {"query": "...", "message": "..."}
```

### 3. Error Handling Test
```bash
curl -s -X POST https://your-api.com/api/v1/query-resume/ \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 422 Validation Error
```

### Automated Smoke Test Script
```bash
#!/bin/bash
# smoke_test.sh

API_URL="${API_URL:-http://127.0.0.1:8000}"

echo "Running smoke tests..."

# Test 1: Health check
echo "Test 1: Health check"
response=$(curl -s -o /dev/null -w "%{http_code}" $API_URL/)
if [ "$response" != "200" ]; then
    echo "FAIL: Health check returned $response"
    exit 1
fi
echo "PASS: Health check"

# Test 2: Query endpoint
echo "Test 2: Query endpoint"
response=$(curl -s -X POST $API_URL/api/v1/query-resume/ \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}')
if echo "$response" | grep -q "message"; then
    echo "PASS: Query endpoint"
else
    echo "FAIL: Query endpoint - $response"
    exit 1
fi

echo "All smoke tests passed!"
```

---

## GitHub Releases (Optional)

Using GitHub CLI:

```bash
# Create release
gh release create v1.0.0 \
  --title "Release v1.0.0" \
  --notes "See CHANGELOG for details"

# Upload assets
gh release upload v1.0.0 ./dist/app.tar.gz
```

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Identify the issue
kubectl logs -l app=rag-resume-chatbot
kubectl describe pod <pod-name>

# 2. Rollback to previous version
kubectl rollout undo deployment/rag-resume-chatbot

# 3. Verify rollback
kubectl rollout status deployment/rag-resume-chatbot

# 4. If using Docker tags:
docker pull registry.example.com/rag-resume-chatbot:v0.9.0
```

---

## Environment Variables Checklist

Ensure these are set in production:
- [ ] `GOOGLE_API_KEY` (or equivalent)
- [ ] `LLM` (default: gemini-2.5-flash)
- [ ] `EMBEDDING_MODEL` (default: gemini-embedding-001)
- [ ] `INDEX_PATH` (default: ./app/data/index)
- [ ] `RESUME_PATH` (default: ./app/data/resume.md)

---

## Summary: Release Workflow

1. **Prepare**: Update CHANGELOG, bump version
2. **Test**: Run full test suite
3. **Tag**: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. **Build**: Build Docker image
5. **Deploy**: Deploy to environment
6. **Smoke Test**: Verify with health/query tests
7. **Push Tag**: `git push origin vX.Y.Z`
8. **Monitor**: Watch logs and metrics

(End of file - total 226 lines)
