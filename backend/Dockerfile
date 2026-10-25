FROM python:3.12-slim

# Optional extras to install, e.g. "postgres" or "postgres,mlflow".
ARG LLMWATCH_EXTRAS="postgres"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # State lives in /data (mount a volume there): SQLite DB + generated secret.
    DATABASE_URL=sqlite+aiosqlite:////data/llmwatch.db \
    SECRET_KEY_FILE=/data/secret_key

# Create a non-root user that owns /data
RUN adduser --disabled-password --gecos '' --uid 10001 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

WORKDIR /app

# Install the package (dependencies + code)
COPY pyproject.toml README.md ./
COPY src ./src
RUN if [ -n "$LLMWATCH_EXTRAS" ]; then pip install ".[$LLMWATCH_EXTRAS]"; else pip install .; fi

# Switch to non-root user
USER appuser
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000
# --no-proxy-headers: X-Forwarded-For is interpreted in one place only
# (llmwatch.rate_limit.client_ip, governed by TRUSTED_PROXIES).
CMD ["uvicorn", "llmwatch.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
