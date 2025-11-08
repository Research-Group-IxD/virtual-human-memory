# syntax=docker/dockerfile:1.6

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:${PATH}"

WORKDIR /app

COPY requirements.txt pyproject.toml uv.lock ./
RUN uv pip install --system -r requirements.txt

COPY common ./common
COPY workers ./workers

ENV PYTHONPATH=/app:/app/common/utils

ARG WORKER_MODULE=workers.vhm_indexer.main
ENV WORKER_MODULE=${WORKER_MODULE}
RUN cat <<'EOF' > /entrypoint.sh
#!/bin/sh
set -e
exec python -m "${WORKER_MODULE}" "$@"
EOF
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

