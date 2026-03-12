FROM python:3.12-slim

# System deps (httpx needs these for SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Output directory (mounted volume or Railway ephemeral storage)
RUN mkdir -p /app/outputs

# notebooklm-py reads auth from this env var on headless environments
# Set NOTEBOOKLM_AUTH_JSON in Railway's variable settings
ENV NOTEBOOKLM_HOME=/app/.notebooklm
ENV OUTPUT_DIR=/app/outputs

CMD ["python", "main.py"]
