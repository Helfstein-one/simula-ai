# Simula-AI Rootless Containerfile for Podman & Docker
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8501

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create non-root user for rootless Podman execution
RUN useradd -u 10001 -m -s /bin/bash simula \
    && chown -R 10001:10001 /app \
    && chmod +x /app/entrypoint.sh

USER simula

EXPOSE 8501

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["ui"]
