# ---------- CogniX Surface – Dockerfile ----------
FROM python:3.12-slim AS base

LABEL maintainer="eliad" \
      description="CogniX Surface – Social Engineering Risk Dashboard"

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NLTK data (punkt tokenizer)
RUN python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)"

# Application code
COPY . .

# Persistent volume for SQLite DB
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/system/status')" || exit 1

CMD ["uvicorn", "app.dashboard:app", "--host", "0.0.0.0", "--port", "8000"]
