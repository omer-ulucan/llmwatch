FROM python:3.12-slim

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

WORKDIR /app

# Install the package (dependencies + code)
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Switch to non-root user
USER appuser

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000
# --no-proxy-headers: X-Forwarded-For is interpreted in one place only
# (llmwatch.rate_limit.client_ip, governed by TRUSTED_PROXIES).
CMD ["uvicorn", "llmwatch.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
