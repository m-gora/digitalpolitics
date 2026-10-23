FROM python:3.12-slim-bookworm AS builder

ARG TARGETARCH

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.28

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

# Compile the site's Tailwind CSS using the same standalone CLI version as the
# project setup, selecting and verifying the binary for the target platform.
RUN case "${TARGETARCH}" in \
        amd64) tailwind_arch=x64; tailwind_sha256=dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a ;; \
        arm64) tailwind_arch=arm64; tailwind_sha256=55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195 ;; \
        *) echo "Unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-linux-${tailwind_arch}" -o /tmp/tailwindcss \
    && echo "${tailwind_sha256}  /tmp/tailwindcss" | sha256sum --check --status \
    && chmod +x /tmp/tailwindcss \
    && /tmp/tailwindcss -i src/dpp/static/css/input.css -o src/dpp/static/css/output.css --minify \
    && rm /tmp/tailwindcss \
    && uv sync --locked --no-dev

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app

COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "dpp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
