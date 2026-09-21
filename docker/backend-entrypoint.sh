#!/bin/sh
set -e
# 1) apply database migrations (PostgreSQL)
alembic upgrade head
# 2) fetch the open Hugging Face checkpoints into the mounted cache if they are not there yet (CPU-sized models)
if [ "${GEC_AUTO_DOWNLOAD:-1}" = "1" ]; then
  python scripts/download_models.py || echo "WARNING: model download incomplete; affected languages will run in degraded mode"
fi
# 3) optional: also fetch the NLLB translator (marked optional in configs/models.yaml) when GEC_DOWNLOAD_TRANSLATOR=1
if [ "${GEC_DOWNLOAD_TRANSLATOR:-0}" = "1" ]; then
  python scripts/download_models.py translator || echo "WARNING: translator download incomplete; Translate will be unavailable"
fi
exec "$@"
