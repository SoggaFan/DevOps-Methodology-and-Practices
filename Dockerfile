# Versioned Python base image; do not replace with a floating `latest` tag.
FROM python:3.12.16-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

# A fixed non-root UID/GID makes runtime ownership predictable.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
       --shell /usr/sbin/nologin app

# Runtime dependencies are explicitly version-pinned in requirements.txt.
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

# Copy only runtime files; local settings and development tools are not in the image.
COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 web/ ./web/

USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM

# Uses Python's standard library, avoiding curl/wget in the runtime image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Exec form lets Uvicorn receive SIGTERM and finish in-flight requests gracefully.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
