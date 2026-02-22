# Backend for AWS (App Runner / ECS / Elastic Beanstalk Docker)
# Build from repo root: docker build -f Dockerfile .
FROM python:3.12-slim

WORKDIR /app

# System deps for sentence-transformers / PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch to keep image smaller and avoid OOM
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Backend deps
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App and data (docs + pre-built index)
COPY backend/ backend/
COPY docs/ docs/

# AWS App Runner uses PORT=8080; override for local (e.g. 8000)
ENV PORT=8080
EXPOSE 8080

# Run from backend dir so imports work
WORKDIR /app/backend
# DOCS_DIR for parent /app/docs
ENV DOCS_DIR=/app/docs
ENV PYTHONUNBUFFERED=1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
