# Multi-stage build — wheels in a build stage, slim runtime image with
# non-root user, embedded HEALTHCHECK, and read-only friendly layout.

# -------------------- BUILD STAGE --------------------
FROM python:3.11-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# -------------------- RUNTIME STAGE --------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/backend \
    PIP_NO_CACHE_DIR=1

# libpq is needed at runtime for psycopg2; everything else comes from wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid app --home-dir /srv/backend --shell /usr/sbin/nologin app

WORKDIR /srv/backend

COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# Application code (chown to non-root user)
COPY --chown=app:app . /srv/backend

USER app

EXPOSE 8000

# Liveness probe — matches /health endpoint added in main.py
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
