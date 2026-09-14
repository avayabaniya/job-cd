# job_cd/core/io.py
import os
import json
import uuid
from pathlib import Path


def read_json(path: Path, default: dict = None) -> dict:
    """Reads JSON from disk. Returns default (or {}) on missing/corrupt files."""
    if not path.exists():
        return default or {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default or {}
    except (json.JSONDecodeError, OSError, UnicodeError):
        return default or {}


def write_json(path: Path, data: dict):
    """Writes JSON to disk using atomic replacement to prevent corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")

    try:
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
