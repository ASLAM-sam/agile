# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependency layer, cached independently of application code so an edit to
# app/ does not reinstall the world.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0" \
      "pydantic>=2.9.0" \
      "pydantic-settings>=2.6.0" \
      "email-validator>=2.2.0" \
      "sqlalchemy[asyncio]>=2.0.36" \
      "alembic>=1.14.0" \
      "asyncpg>=0.30.0" \
      "aiosqlite>=0.20.0" \
      "greenlet>=3.1.0" \
      "anthropic>=0.40.0" \
      "pyjwt>=2.10.0" \
      "bcrypt>=4.2.0" \
      "python-multipart>=0.0.17" \
      "httpx>=0.27.0"

COPY app ./app

# Migrations ship with the image so `docker compose exec api alembic upgrade
# head` works against the running container.
COPY alembic.ini ./
COPY alembic ./alembic

# Artifact storage. Declared as a volume so generated packages survive a
# container replacement.
RUN mkdir -p /app/artifacts

# Run as a non-root user.
RUN useradd --create-home --uid 1001 aegis && chown -R aegis:aegis /app
USER aegis

VOLUME ["/app/artifacts"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
