FROM python:3.9.19-slim

# Set the working directory
WORKDIR /service

# Install system dependencies (less frequently changed)
RUN apt-get update --yes && \
    apt-get upgrade --yes && \
    apt-get install --yes --no-install-recommends \
    python3-dev \
    gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip==25.0.1

# Copy the requirements file (first to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies (cached if requirements.txt doesn't change)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (more frequently changed)
COPY . /service

# Expose the port that the app will listen on
EXPOSE 8000
WORKDIR /service

ENV PORT=8000
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Use gunicorn to start the FastAPI app (referencing $PORT)
CMD gunicorn --bind 0.0.0.0:$PORT --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker main:app