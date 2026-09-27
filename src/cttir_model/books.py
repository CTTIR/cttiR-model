"""Local-only book indexing. Book knowledge never establishes R API approval."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .errors import ProjectError
from .provenance import atomic_json, fingerprint, read_json


def library_manifest(root: Path) -> dict:
    value = read_json(root / "manifest.json")
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("visibility") != "local_only" or not isinstance(value.get("sources"), list):
        raise ProjectError("book_manifest", "Expected a local-only book source manifest.")
    if not 1 <= len(value["sources"]) <= 20:
        raise ProjectError("book_limit", "The laptop library supports at most 20 registered PDFs.")
    seen = set()
    for source in value["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            raise ProjectError("book_manifest", "Malformed book source.")
        if (not isinstance(source.get("title"), str) or not source["title"].strip()
                or source.get("rights_status") not in {"pending_review", "approved", "restricted", "rejected"}
                or type(source.get("training_requested_by_user")) is not bool):
            raise ProjectError("book_manifest", "Book titles, rights states and requested-use markers must be explicit.")
        name = Path(source["path"])
        path = root / name
        if (name.is_absolute() or len(name.parts) != 1 or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root.resolve()) or path.suffix.lower() != ".pdf"):
            raise ProjectError("book_path", "Registered books must be ordinary local PDFs within the library.")
        if source.get("source_id") in seen or source.get("source_id") != "book:" + str(source.get("sha256")):
            raise ProjectError("book_manifest", "Book identities must be unique SHA-256 source IDs.")
        if not re.fullmatch(r"[a-f0-9]{64}", str(source.get("sha256", ""))) or source.get("redistribution_allowed") is not False:
            raise ProjectError("book_manifest", "Books require source hashes and local-only distribution policy.")
        if (type(source.get("pages")) is not int or not 1 <= source["pages"] <= 5000
                or type(source.get("bytes")) is not int or not 1 <= source["bytes"] <= 100 * 1024 * 1024):
            raise ProjectError("book_limit", "Book metadata exceeds the small local-library limits.")
        seen.add(source["source_id"])
    return value


def verify_book(path: Path, source: dict) -> None:
    if path.stat().st_size != source["bytes"]:
        raise ProjectError("book_changed", "Book size differs from its registered copy.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != source["sha256"]:
        raise ProjectError("book_changed", "Book content changed after registration.")


def extract_text(path: Path) -> str:
    if not all(shutil.which(tool) for tool in ("prlimit", "nice", "pdftotext")):
        raise ProjectError("pdf_backend", "This bounded extractor requires Poppler, nice and prlimit.")
    with tempfile.TemporaryDirectory(prefix="cttir-book-") as directory:
        output = Path(directory) / "text.txt"
        args = ["prlimit", "--as=536870912", "--cpu=10", "--fsize=16777216", "--nofile=128", "--",
                "nice", "-n", "10", "pdftotext", "-layout", "-enc", "UTF-8", str(path), str(output)]
        try:
            result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, timeout=15)
        except subprocess.TimeoutExpired as exc:
            raise ProjectError("pdf_budget", "Book text extraction exceeded its budget; use smaller page batches later.") from exc
        if result.returncode or not output.is_file() or output.stat().st_size > 16777216:
            raise ProjectError("pdf_extraction", "Bounded PDF text extraction failed; no OCR or unbounded fallback was attempted.")
        return output.read_text(encoding="utf-8")


def chunk_pages(text: str, source: dict) -> list[dict]:
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) != source["pages"]:
        raise ProjectError("pdf_pages", "Extracted page count differs from registered PDF metadata.")
    chunks = []
    for number, text in enumerate(pages, 1):
        text = re.sub(r"[\x00-\x08\x0b\x0e-\x1f]", "", text).strip()
        for offset in range(0, len(text), 3000):
            content = text[offset:offset + 3000]
            if not content.strip():
                continue
            chunk = {"source_id": source["source_id"], "source_sha256": source["sha256"],
                     "title": source["title"], "pdf_page": number, "character_offset": offset,
                     "text": content, "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                     "source_kind": "book", "local_only": True, "api_verification": False,
                     "review_status": "unreviewed", "rights_status": source["rights_status"],
                     "training_requested_by_user": source["training_requested_by_user"]}
            chunk["chunk_id"] = "book-chunk:" + fingerprint(chunk)
            chunks.append(chunk)
    return chunks


def ingest_library(root: Path) -> dict:
    manifest = library_manifest(root)
    counts = []
    for source in manifest["sources"]:
        path = root / source["path"]
        verify_book(path, source)
        target = root / "index" / (source["sha256"] + ".json")
        metadata_pin = fingerprint(source)
        if target.exists():
            existing = read_json(target, 32 * 1024 * 1024)
            if existing.get("source_manifest_sha256") == metadata_pin:
                checked_chunks(existing, source["source_id"])
                snapshot = root / "snapshots" / (fingerprint(existing) + ".json")
                if not snapshot.exists():
                    atomic_json(snapshot, existing)
                counts.append({"source_id": source["source_id"], "pages": source["pages"], "chunks": len(existing["chunks"]), "reused": True})
                continue
        chunks = chunk_pages(extract_text(path), source)
        payload = {"schema_version": 1, "source_id": source["source_id"], "source_manifest_sha256": metadata_pin,
                   "chunks": chunks, "index_sha256": fingerprint(chunks), "training_ready": False}
        atomic_json(root / "snapshots" / (fingerprint(payload) + ".json"), payload)
        atomic_json(target, payload)
        counts.append({"source_id": source["source_id"], "pages": source["pages"], "chunks": len(chunks), "reused": False})
    return {"status": "locally_indexed", "books": counts, "training_ready": False,
            "model_calls": 0, "redistribution_allowed": False}


def checked_chunks(index: dict, source_id: str) -> list[dict]:
    if not isinstance(index, dict) or index.get("source_id") != source_id or not isinstance(index.get("chunks"), list):
        raise ProjectError("book_index", "Book index is malformed.")
    chunks = index["chunks"]
    if fingerprint(chunks) != index.get("index_sha256"):
        raise ProjectError("book_index", "Book index content hash is stale.")
    for chunk in chunks:
        if (chunk.get("source_id") != source_id or chunk.get("local_only") is not True
                or chunk.get("api_verification") is not False
                or chunk.get("chunk_id") != "book-chunk:" + fingerprint({k: v for k, v in chunk.items() if k != "chunk_id"})):
            raise ProjectError("book_index", "Book chunk provenance differs from its identity.")
    return chunks


def search_library(root: Path, query: str, limit: int = 5) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000 or not 1 <= limit <= 10:
        raise ProjectError("book_query", "Supply a nonempty short query and 1–10 result limit.")
    manifest = library_manifest(root)
    tokens = set(re.findall(r"\w+", query.casefold()))
    candidates = []
    for source in manifest["sources"]:
        verify_book(root / source["path"], source)
        index = read_json(root / "index" / (source["sha256"] + ".json"), 32 * 1024 * 1024)
        if index.get("source_manifest_sha256") != fingerprint(source):
            raise ProjectError("book_index", "Book source metadata changed; rebuild the local index.")
        for chunk in checked_chunks(index, source["source_id"]):
            words = set(re.findall(r"\w+", chunk["text"].casefold()))
            score = len(tokens & words)
            if score:
                candidates.append((-score, chunk["chunk_id"], chunk))
    return {"status": "retrieved", "local_only": True, "api_verification": False,
            "chunks": [chunk for _, _, chunk in sorted(candidates)[:limit]],
            "training_ready": False}


def training_plan(root: Path) -> dict:
    manifest = library_manifest(root)
    sources = []
    for source in manifest["sources"]:
        index = read_json(root / "index" / (source["sha256"] + ".json"), 32 * 1024 * 1024)
        if index.get("source_manifest_sha256") != fingerprint(source):
            raise ProjectError("book_index", "Book metadata changed; rebuild before preparing a training plan.")
        chunks = checked_chunks(index, source["source_id"])
        sources.append({"source_id": source["source_id"], "source_sha256": source["sha256"],
                        "title": source["title"], "pages_available": source["pages"],
                        "chunks_available": len(chunks), "index_sha256": index["index_sha256"],
                        "grouping_lineage": source["source_id"], "rights_status": source["rights_status"],
                        "content_status": source.get("completeness", "unreviewed"),
                        "training_use": "awaiting_body_chapters" if source.get("completeness") == "front_matter_only" else "reviewed_tasks_requested"})
    result = {"schema_version": 1, "status": "preparation_only", "local_only": True,
              "sources": sources, "training_examples_created": 0, "training_ready": False,
              "requirements": ["Retain source hash, chunk ID and PDF page in each task's source-review manifest.",
                               "Review extracted formulas/tables against PDF pages before deriving scientific tasks.",
                               "Write and independently review original supervised tasks; source text is not a reviewed answer.",
                               "Keep book/chapter/template lineage together before splitting; seal held-out tasks.",
                               "Validate all R APIs against approved exact package versions and preserve cttiR approvals.",
                               "Keep book-derived artifacts local; source rights/distribution review remains distinct.",
                               "Execute actual training only after the deferred effective-base, hardware and baseline gates."]}
    atomic_json(root / "training-plan.json", result)
    return result
