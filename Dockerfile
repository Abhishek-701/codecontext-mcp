FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies before copying src/ so this layer is cached until pyproject.toml changes.
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    asyncpg \
    fastmcp \
    watchdog \
    tree-sitter \
    tree-sitter-python \
    tree-sitter-javascript \
    sentence-transformers

COPY src/ ./src/
COPY docs/ ./docs/

ENV PYTHONPATH=/app
