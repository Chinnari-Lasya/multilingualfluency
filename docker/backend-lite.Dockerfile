FROM python:3.12-slim
# Rules-only backend for small hosts (e.g. Render's free 512 MB plan). No PyTorch / transformers are installed,
# so no AI model is ever loaded: O2 falls back to rule-based fixes and O3 fails closed (abstains), by design.
# The full image with the neural models is docker/backend.Dockerfile.

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models/hf_cache GEC_HOME=/models GEC_CONFIG_DIR=/app/configs
# Production-safe default: do NOT seed the demo learner/educator/admin accounts (password "demo"). Override with 1 for local Docker.
ENV GEC_SEED_DEMO_USERS=0
# No models to fetch: skip the entrypoint's Hugging Face download step.
ENV GEC_AUTO_DOWNLOAD=0 GEC_DOWNLOAD_TRANSLATOR=0
WORKDIR /app
RUN mkdir -p /models

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e ".[api]" alembic
# Fail the build early if the PostgreSQL driver (psycopg[binary], from the `api` extra) is missing.
RUN python -c "import psycopg, sqlalchemy; sqlalchemy.create_engine('postgresql+psycopg://u:p@h/db'); print('psycopg', psycopg.__version__, psycopg.pq.__impl__)"

COPY configs ./configs
COPY data ./data
COPY scripts ./scripts
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/backend-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "gec_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
