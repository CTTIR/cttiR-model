"""Small, immutable local evidence snapshots. No fetching or R execution."""

import hashlib
import re
from pathlib import Path

from .config import Config, validate
from .errors import ProjectError
from .provenance import atomic_json, fingerprint, read_json


def package_key(pin: dict) -> tuple[str, str, str]:
    return pin["name"], pin["version"], pin["repository"]


def check_corpus(value: dict, require_usable: bool = True) -> dict:
    validate(value, "corpus")
    ids = set()
    usable = 0
    for document in value["documents"]:
        identity = document["evidence_id"]
        if identity in ids:
            raise ProjectError("duplicate_evidence", "Evidence IDs must be unique within a snapshot.")
        ids.add(identity)
        if hashlib.sha256(document["content"].encode()).hexdigest() != document["content_sha256"]:
            raise ProjectError("content_hash", "A corpus document does not match its content hash.")
        usable += approved(document)
    if require_usable and not usable:
        raise ProjectError("empty_approved_corpus", "No approved document content is available; metadata candidates are not evidence.")
    return {"documents": len(ids), "approved_documents": usable,
            "excluded_documents": len(ids) - usable, "fixture_only": value["fixture_only"]}


def approved(document: dict) -> bool:
    return document["review_status"] == "approved" and document["rights_status"] == "approved"


class Corpus:
    def __init__(self, value: dict, snapshot_id: str):
        self.coverage = check_corpus(value)
        actual = "sha256:" + fingerprint(value)
        if snapshot_id != actual:
            raise ProjectError("corpus_pin", "The configured corpus pin does not match snapshot content.")
        self.snapshot_id = actual
        self.fixture_only = value["fixture_only"]
        self.documents = {d["evidence_id"]: d for d in value["documents"] if approved(d)}

    @classmethod
    def from_config(cls, config: Config) -> "Corpus":
        settings = config.values["corpus"]
        if not settings["path"] or not settings["snapshot_id"]:
            raise ProjectError("missing_corpus", "Configure an immutable corpus path and snapshot_id after ingestion.")
        return cls(read_json(config.path(settings["path"]), config.limit), settings["snapshot_id"])

    def evidence(self, ids: list[str], pins: list[dict]) -> list[dict]:
        keys = [package_key(pin) for pin in pins]
        if len(keys) != len(set(keys)) or len({pin["name"] for pin in pins}) != len(keys):
            raise ProjectError("package_pin", "Each package needs one unambiguous version and repository pin.")
        result = []
        for identity in ids:
            document = self.documents.get(identity)
            if document is None:
                raise ProjectError("unknown_evidence", "Evidence is absent or not approved in the pinned snapshot.")
            if package_key(document["package"]) not in keys:
                raise ProjectError("package_pin", "Evidence does not match the supplied package pins.")
            result.append(document)
        return result

    def search(self, query: str, pin: dict, limit: int = 5, max_chars: int = 16000) -> list[dict]:
        if len(query) > 20000 or not 1 <= limit <= 20 or not 1 <= max_chars <= 100000:
            raise ProjectError("search_budget", "Retrieval budget is out of bounds.")
        tokens = set(re.findall(r"[\w.]+", query.casefold()))
        ranked = []
        for document in self.documents.values():
            if package_key(document["package"]) != package_key(pin):
                continue
            symbol = document["symbol"]
            exact = query.strip() in {symbol, f'{pin["name"]}::{symbol}'}
            words = set(re.findall(r"[\w.]+", (symbol + " " + document["content"]).casefold()))
            score = 1000 * exact + len(tokens & words)
            if score:
                ranked.append((-score, document["evidence_id"], document))
        result, used = [], 0
        for _, _, document in sorted(ranked):
            # Preserve entire signatures and evidence; never silently cut off a prerequisite.
            size = len(document["content"]) + len(document["signature"])
            if used + size > max_chars:
                continue
            result.append(document)
            used += size
            if len(result) >= limit:
                break
        return result


def ingest(config: Config, source: Path) -> dict:
    value = read_json(source, config.limit)
    coverage = check_corpus(value)
    digest = fingerprint(value)
    path = config.artifacts / "corpus" / (digest + ".json")
    if path.exists():
        if fingerprint(read_json(path, config.limit)) != digest:
            raise ProjectError("snapshot_corrupt", "Existing snapshot is corrupt; refusing to overwrite it.")
    else:
        atomic_json(path, value)
    # Activation is explicit through config, so failed imports cannot replace old pins.
    return {"status": "implemented", "snapshot_id": "sha256:" + digest,
            "path": str(path), "coverage": coverage, "activated": False,
            "training_ready": False}
