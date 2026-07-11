FROM python:3.11-slim

LABEL org.opencontainers.image.title="paperless-chandra"
LABEL org.opencontainers.image.description="Re-OCR Paperless-NGX documents with Chandra 2 (Datalab API or vLLM)"
LABEL org.opencontainers.image.source="https://github.com/chirimoyas/paperless-chandra"

# Install system deps for PyMuPDF
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Config volume (mount your .env or config file here)
VOLUME /config

# Default: run as continuous poller
ENTRYPOINT ["python", "-m", "chandra_paperless"]
CMD ["--config", "/config/chandra-paperless.json"]