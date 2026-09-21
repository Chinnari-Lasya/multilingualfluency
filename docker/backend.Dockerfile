FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models/hf_cache GEC_HOME=/models GEC_CONFIG_DIR=/app/configs
# Production-safe default: do NOT seed the demo learner/educator/admin accounts (password "demo"). Override with 1 for local Docker.
ENV GEC_SEED_DEMO_USERS=0
WORKDIR /app

# CPU-only PyTorch (no CUDA dependency; the system falls back to CPU by design)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e ".[ml,api]" alembic

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
