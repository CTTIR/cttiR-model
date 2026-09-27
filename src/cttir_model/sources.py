"""Bounded R source-archive extraction into a review queue, never approval."""

import hashlib
import io
import re
import tarfile
from pathlib import Path, PurePosixPath

from .errors import ProjectError
from .r_validation import run_worker


def read_archive(path: Path, byte_limit: int = 8 * 1024 * 1024) -> dict[str, bytes]:
    if path.stat().st_size > byte_limit:
        raise ProjectError("archive_limit", "Source archive exceeds the small-import budget.")
    result, total = {}, 0
    try:
        with tarfile.open(path, "r:*") as archive:
            for index, entry in enumerate(archive):
                relative = PurePosixPath(entry.name)
                if index >= 2000 or relative.is_absolute() or ".." in relative.parts or "\\" in entry.name:
                    raise ProjectError("unsafe_archive", "Unsafe path or too many archive members.")
                if entry.isdir():
                    continue
                if not entry.isfile() or entry.name in result:
                    raise ProjectError("unsafe_archive", "Links, special files and duplicate paths are not accepted.")
                total += entry.size
                if entry.size > 1024 * 1024 or total > byte_limit:
                    raise ProjectError("archive_limit", "Expanded archive exceeds the import budget.")
                stream = archive.extractfile(entry)
                if stream is None:
                    raise ProjectError("unsafe_archive", "Archive member cannot be read.")
                result[entry.name] = stream.read(entry.size + 1)
    except (tarfile.TarError, EOFError) as exc:
        raise ProjectError("invalid_archive", "Source archive is malformed.") from exc
    return result


def parse_description(raw: bytes) -> dict:
    fields = {}
    current = None
    for line in raw.decode("utf-8").splitlines():
        if line.startswith((" ", "\t")) and current:
            fields[current] += " " + line.strip()
        elif ":" in line:
            current, value = line.split(":", 1)
            if current in fields:
                raise ProjectError("description", "Duplicate DESCRIPTION field.")
            fields[current] = value.strip()
    if any(not fields.get(key) for key in ("Package", "Version", "License")):
        raise ProjectError("description", "DESCRIPTION needs Package, Version and License.")
    return fields


def extract_candidates(path: Path, repository: str, max_topics: int = 20) -> dict:
    if not 1 <= max_topics <= 100 or not repository:
        raise ProjectError("source_budget", "Supply a repository and a 1–100 topic budget.")
    members = read_archive(path)
    descriptions = [name for name in members if PurePosixPath(name).name == "DESCRIPTION"]
    if len(descriptions) != 1:
        raise ProjectError("description", "Expected one package DESCRIPTION.")
    root = str(PurePosixPath(descriptions[0]).parent)
    metadata = parse_description(members[descriptions[0]])
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    topics = sorted(name for name in members if name.startswith(root + "/man/") and name.endswith(".Rd"))
    documents, failures = [], []
    for name in topics[:max_topics]:
        try:
            text = run_worker("rd", members[name].decode("utf-8"))
            if text.startswith("STATUS\t") or not text.strip():
                raise ProjectError("rd_rejected", "Invalid or dynamic Rd content.")
            document = {"evidence_id": "candidate:" + hashlib.sha256((source_hash + name).encode()).hexdigest(),
                        "package": {"name": metadata["Package"], "version": metadata["Version"], "repository": repository},
                        "symbol": PurePosixPath(name).stem, "signature": "Unverified Rd topic; callable signature pending review",
                        "kind": "reference", "content": text, "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "source_locator": "archive-sha256:" + source_hash + "/" + name,
                        "source_revision": source_hash, "license": metadata["License"],
                        "rights_status": "pending", "review_status": "candidate"}
            documents.append(document)
        except (ProjectError, UnicodeError) as exc:
            failures.append({"member": name, "reason": exc.code if isinstance(exc, ProjectError) else "encoding"})
    namespace = members.get(root + "/NAMESPACE", b"").decode("utf-8", errors="replace")
    exports = re.findall(r'^export\(([A-Za-z.][A-Za-z0-9._]*)\)\s*$', namespace, flags=re.MULTILINE)
    return {"corpus": {"schema_version": 1, "fixture_only": False, "documents": documents},
            "source": {"archive_sha256": source_hash, "package": metadata["Package"], "version": metadata["Version"],
                       "license": metadata["License"], "literal_exports": exports,
                       "namespace_complete": False, "topics_total": len(topics),
                       "topics_deferred": max(0, len(topics) - max_topics), "failures": failures,
                       "vignettes": [n for n in members if n.startswith(root + "/vignettes/")],
                       "training_ready": False, "approval": "pending"}}
