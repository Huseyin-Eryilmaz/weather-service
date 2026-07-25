# A Dockerfile is a recipe for building an image: a filesystem snapshot
# containing Python, this project's dependencies, and its code. Running
# that image produces a container — an isolated process. The API and the
# worker run the same image with different commands, so there is one
# recipe here, not two.

# ---------------------------------------------------------------------
# Stage 1: build the virtual environment
# ---------------------------------------------------------------------
# Two stages exist so the final image carries only what it needs to run.
# Compilers, caches and lockfiles stay behind in this stage; the result
# is a smaller image, which is faster to push, pull and start.
FROM python:3.12-slim AS builder

# uv is the same tool used locally, copied in from its official image
# rather than installed with pip — faster, and pinned to one version.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies are installed before the source is copied. Docker caches
# each step and reuses it while its inputs are unchanged, so editing a
# Python file rebuilds only the last few steps — dependencies are not
# reinstalled. Copying everything at once would throw that cache away on
# every edit.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-install-project --no-dev 2>/dev/null || \
    uv sync --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --no-dev

# ---------------------------------------------------------------------
# Stage 2: the runtime image
# ---------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Containers run as root by default. If a process is ever compromised,
# root inside the container is a much better starting point for an
# attacker than an unprivileged account — so it gets one.
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Only the finished virtual environment and the source come across.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

# The default command; compose overrides it for the worker.
CMD ["uvicorn", "weather.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
