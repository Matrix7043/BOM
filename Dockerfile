# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NUMBA_CACHE_DIR=/tmp/numba-cache \
    MPLCONFIGDIR=/tmp/mpl

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- test image: `docker compose run --rm tests` ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY app ./app
COPY data ./data
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]

# ---- runtime image ----
FROM base AS runtime
RUN useradd --create-home --uid 10001 appuser
COPY app ./app
COPY data ./data
RUN mkdir -p /srv/storage && chown appuser /srv/storage
USER appuser

ENV PORT=8000 DATA_DIR=/srv/data STORAGE_DIR=/srv/storage
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers"]
