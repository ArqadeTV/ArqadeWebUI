"""Tiny JSON persistence under ~/.arqade (override with ARQADE_HOME)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_lock = threading.RLock()

DEFAULT_SETTINGS: dict[str, Any] = {
    "extra_roots": [],
    "ollama_url": "http://127.0.0.1:11434",
    "openai_endpoints": [
        {"name": "LM Studio", "base_url": "http://127.0.0.1:1234/v1", "api_key": ""},
        {"name": "llama.cpp server", "base_url": "http://127.0.0.1:8080/v1", "api_key": ""},
    ],
    "detect_dark_extensions": True,
}


def data_dir() -> Path:
    p = Path(os.environ.get("ARQADE_HOME") or Path.home() / ".arqade")
    p.mkdir(parents=True, exist_ok=True)
    return p


def read(name: str, default: Any) -> Any:
    path = data_dir() / name
    with _lock:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default


def write(name: str, value: Any) -> None:
    path = data_dir() / name
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(value, fh, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def get_settings() -> dict[str, Any]:
    saved = read("settings.json", {})
    return {**DEFAULT_SETTINGS, **(saved if isinstance(saved, dict) else {})}


def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
    merged = get_settings()
    for key in DEFAULT_SETTINGS:
        if key in patch:
            merged[key] = patch[key]
    write("settings.json", merged)
    return merged
