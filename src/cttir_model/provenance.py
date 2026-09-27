"""Bounded input, canonical hashes and crash-safe local artifacts."""

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ProjectError


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProjectError("invalid_json", "Duplicate JSON object key.")
        result[key] = value
    return result


def decode_json(raw: bytes) -> Any:
    try:
        def invalid_constant(value: str) -> None:
            raise ValueError("Non-finite number")
        def finite_float(value: str) -> float:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Non-finite number")
            return number
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProjectError("invalid_json", "Expected valid UTF-8 JSON.") from exc


def read_json(path: Path, limit: int = 2097152) -> Any:
    if not path.is_file():
        raise ProjectError("missing_input", "Required input file is absent.")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ProjectError("input_limit", "Input exceeds the configured size limit.")
    return decode_json(raw)


def atomic_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                         allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pending-", delete=False) as stream:
            name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def record_phase(root: Path, entry: dict) -> None:
    """Single-writer ledger; individual entries remain immutable after interruption."""
    directory = root / "implementation"
    digest = fingerprint(entry)
    atomic_json(directory / (digest + ".json"), entry)
    # Reconstruct the index from entries, including any written before a crash.
    entries = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "ledger.json":
            continue
        if len(path.stem) != 64:
            continue
        item = read_json(path)
        if fingerprint(item) != path.stem:
            raise ProjectError("ledger_corrupt", "Historical phase evidence does not match its hash.")
        entries.append({"sha256": path.stem, **item})
    atomic_json(directory / "ledger.json", {"schema_version": 1, "entries": entries})
