FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (less frequently changed)
RUN apt-get update --yes && \
    apt-get upgrade --yes && \
    apt-get install --yes --no-install-recommends \
    python3-dev \
    gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible installs (parity with local `uv venv` contract)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the requirements file (first to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies (cached if requirements.txt doesn't change)
RUN uv pip install --system --no-cache -r requirements.txt

# Copy the application code (more frequently changed)
COPY . /app

ARG PORTFOLIO_INDEX_BUILD_DATE
ENV PORTFOLIO_INDEX_BUILD_DATE=${PORTFOLIO_INDEX_BUILD_DATE}

# Bake a fresh deterministic retrieval index so image rebuilds carry it.
# The live LlamaIndex store under app/data/index/ is refreshed beforehand
# with `make docker-build` (runs `make reindex`, needs GOOGLE_API_KEY);
# no file watcher by default.
RUN python build_index.py

# Expose the port that the app will listen on
EXPOSE 8000
WORKDIR /app

ENV PORT=8000
ENV WORKERS=1
ENV PYTHONPATH="/app"

# Use gunicorn to start the FastAPI app (referencing $PORT).
# Exec form with `sh -c` + `exec` so $PORT/${WORKERS:-1} expand at
# container runtime while gunicorn still runs as PID 1 for clean signals.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${WORKERS:-1} --worker-class uvicorn.workers.UvicornWorker main:app"]
