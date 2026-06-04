# Multi-stage with uv: deps are resolved + installed in a builder stage
# against the project's uv.lock (reproducible — never freshly resolved at
# build time), then copied into a slim runtime stage so the final image
# carries no build tooling.

FROM ghcr.io/astral-sh/uv:0.5-python3.12-bookworm-slim AS builder
WORKDIR /app

# Bytecode-compile installed packages for faster cold-start; don't try to
# hardlink from the host cache (won't work across mount boundaries).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/install

# Install deps before the source so editing app code doesn't bust the cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/install/bin:$PATH \
    PYTHONPATH=/app

# psycopg2-binary already ships libpq, so no apt deps are needed for the
# runtime image. Non-root user is defense-in-depth.
RUN useradd --uid 10001 --create-home app
COPY --from=builder /install /install
COPY --from=builder --chown=app:app /app /app

USER app
EXPOSE 8000
# `--proxy-headers` lets the app trust X-Forwarded-* from Fly's edge so it
# builds correct absolute URLs behind the load balancer.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
