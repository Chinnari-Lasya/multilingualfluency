"""Download only the weights the registry needs into HF_HOME (outside the repo). Idempotent.

Usage: python scripts/download_models.py [model_key ...]   (default: all keys in configs/models.yaml)
"""
from __future__ import annotations

import sys

from huggingface_hub import HfApi, snapshot_download

from gec_common.config import load_models_config


def main(keys: list[str]) -> int:
    cfg = load_models_config()["models"]
    keys = keys or [k for k, v in cfg.items() if not v.get("optional")]  # optional models only when named explicitly
    api, rc = HfApi(), 0
    for k in keys:
        hf_id = cfg[k]["hf_id"]
        files = {s.rfilename for s in api.model_info(hf_id).siblings}
        weights = ("model.safetensors" if "model.safetensors" in files else "pytorch_model.bin")
        allow = ["*.json", "*.model", "*.txt", "*.py", "tokenizer*", "spiece*", "sentencepiece*", weights]
        print(f"[{k}] {hf_id}  weights={weights}", flush=True)
        try:
            path = snapshot_download(hf_id, allow_patterns=allow)
            print(f"   -> {path}", flush=True)
        except Exception as e:  # keep going; report at the end
            print(f"   FAILED: {e}", flush=True)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
