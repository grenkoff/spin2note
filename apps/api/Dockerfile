# Multi-stage build: compile the Rust hh_parser extension, then a slim runtime.
# Cloud-agnostic: plain Docker image, configured entirely via env vars.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder
WORKDIR /app

# Rust toolchain for building the hh_parser PyO3 extension via maturin.
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

# Python deps (cached layer).
COPY apps/api/pyproject.toml apps/api/
RUN cd apps/api && uv sync --no-install-project

# Build & install the Rust extension.
COPY crates/ crates/
RUN cd apps/api && uv run maturin build --release --manifest-path ../../crates/hh-parser/Cargo.toml \
    && uv pip install ../../target/wheels/hh_parser-*.whl

# App source.
COPY apps/api/ apps/api/
RUN cd apps/api && uv sync

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app/apps/api
# libarchive13: archive extraction (zip/rar/7z/tar/...) via libarchive-c.
RUN apt-get update && apt-get install -y --no-install-recommends libarchive13 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/app/apps/api/.venv/bin:${PATH}"
COPY --from=builder /app/apps/api/.venv /app/apps/api/.venv
COPY --from=builder /app/apps/api/src /app/apps/api/src

EXPOSE 8000
CMD ["uvicorn", "spin2note_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
