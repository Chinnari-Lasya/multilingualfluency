"""Config loading. Large artifacts (HF cache, data, venv) live under GEC_HOME, outside the repo."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .schemas import CapabilityInfo

_REPO_ROOT = Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    return Path(os.environ.get("GEC_CONFIG_DIR", _REPO_ROOT / "configs"))


def gec_home() -> Path:
    """Root for models/data/artifacts. Default is outside the repo tree if GEC_HOME is set."""
    return Path(os.environ.get("GEC_HOME", _REPO_ROOT / "var"))


@lru_cache(maxsize=1)
def load_models_config() -> dict[str, Any]:
    with open(config_dir() / "models.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def model_spec(key: str) -> dict[str, Any]:
    cfg = load_models_config()["models"]
    if key not in cfg:
        raise KeyError(f"unknown model key {key!r}")
    return {"key": key, **cfg[key]}


def thresholds(section: str) -> dict[str, Any]:
    return load_models_config()["thresholds"][section]


def language_capability(lang: str) -> CapabilityInfo:
    cfg = load_models_config()
    entry = cfg["languages"][lang]
    gen = entry.get("generator")
    lic = cfg["models"][gen].get("license") if gen else None
    lic_note = None
    if lic == "unspecified":
        lic_note = "Model licence is unspecified on the Hugging Face Hub; verify before non-research use."
    return CapabilityInfo(
        language=lang,
        level=entry["capability"],
        model_id=cfg["models"][gen]["hf_id"] if gen else None,
        summary=entry["summary"],
        limitations=list(entry.get("limitations", [])),
        license_note=lic_note,
    )


def clear_config_cache() -> None:
    load_models_config.cache_clear()
