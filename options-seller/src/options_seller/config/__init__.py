"""Configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DEFAULTS_PATH = Path(__file__).with_name("defaults.yaml")


def load_defaults(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _DEFAULTS_PATH
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_config(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not overrides:
        return dict(base)
    out = dict(base)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_config(out[k], v)
        else:
            out[k] = v
    return out
