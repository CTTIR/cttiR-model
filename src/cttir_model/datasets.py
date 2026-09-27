"""Review, provenance and split checks; never automatically approve examples."""

import re
from collections import Counter

from .config import validate
from .corpus import Corpus
from .errors import ProjectError
from .provenance import fingerprint


def _registry_check(registry: dict) -> None:
    if not isinstance(registry, dict) or set(registry) != {"schema_version", "sources", "validations"} or registry["schema_version"] != 1:
        raise ProjectError("review_registry", "Expected review registry version 1.")
    for section, required in {
        "sources": {"id", "rights_status", "license", "reviewer", "record_sha256"},
        "validations": {"id", "status", "reviewer", "record_sha256"},
    }.items():
        rows = registry[section]
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ProjectError("review_registry", "Review registry sections must be bounded lists.")
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != required
                    or any(not isinstance(v, str) or not v.strip() for v in row.values())
                    or not re.fullmatch(r"[a-f0-9]{64}", row["record_sha256"])
                    or row["id"] in seen):
                raise ProjectError("review_registry", "Malformed or duplicate review registry entry.")
            seen.add(row["id"])


def validate_dataset(records: list[dict], corpus: Corpus, registry: dict) -> dict:
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        raise ProjectError("dataset_size", "Expected 1–1000 records in this bounded CPU validator.")
    _registry_check(registry)
    if corpus.fixture_only:
        raise ProjectError("fixture_corpus", "Synthetic corpus fixtures cannot qualify a training dataset.")
    sources = {r["id"]: r for r in registry["sources"]}
    validations = {r["id"]: r for r in registry["validations"]}
    ids, groups, normalized, prompts = set(), {}, {}, []
    for record in records:
        validate(record, "training-record")
        if record["review_status"] != "reviewed" or record["rights_status"] != "approved" or record["split"] == "unassigned":
            raise ProjectError("unreviewed_record", "Draft, unassigned or rights-unapproved records cannot enter the dataset.")
        if not record["synthetic_data"]:
            raise ProjectError("data_policy", "This profile accepts synthetic-data tasks only.")
        if record["record_id"] in ids:
            raise ProjectError("duplicate_record", "Record IDs must be unique.")
        ids.add(record["record_id"])
        if record["corpus_id"] != corpus.snapshot_id:
            raise ProjectError("corpus_pin", "Dataset corpus pin does not match approved evidence.")
        corpus.evidence(record["evidence_ids"], record["package_pins"])
        expected = record["expected_response"]
        if not set(expected["evidence_ids"]).issubset(record["evidence_ids"]):
            raise ProjectError("invented_evidence", "Expected answer references evidence absent from the record.")
        if expected["status"] == "proposed" and not expected["evidence_ids"]:
            raise ProjectError("ungrounded_proposal", "Positive examples require approved evidence.")
        if (record["messages"][-1]["role"] != "assistant"
                or not any(m["role"] == "user" for m in record["messages"])):
            raise ProjectError("messages", "Records need a user task and final assistant answer.")
        from .provenance import decode_json
        answer = decode_json(record["messages"][-1]["content"].encode())
        if answer != expected:
            raise ProjectError("answer_mismatch", "Final assistant content differs from the reviewed expected response.")
        digest = fingerprint(record)
        source = sources.get(record["source_manifest_id"])
        validation = validations.get(record["validation_id"])
        if not source or source["rights_status"] != "approved" or source["record_sha256"] != digest:
            raise ProjectError("source_review", "Missing or stale record-bound source-rights review.")
        if not validation or validation["status"] != "passed" or validation["record_sha256"] != digest:
            raise ProjectError("validation_review", "Missing or stale record-bound validation evidence.")
        split, group = record["split"], record["group_id"]
        if group in groups and groups[group] != split:
            raise ProjectError("split_leakage", "A task family appears in multiple splits.")
        groups[group] = split
        # Compare task inputs, not common abstention answers. Normalize case,
        # punctuation and numerical variations to catch repeated task templates.
        prompt = " ".join(m["content"] for m in record["messages"] if m["role"] == "user")
        tokens = re.findall(r"\w+", re.sub(r"\d+", "NUMBER", prompt.casefold()))
        key = " ".join(tokens)
        if key in normalized:
            raise ProjectError("duplicate_prompt", "Normalized task prompts overlap; quarantine duplicate templates.")
        normalized[key] = split
        shingles = {tuple(tokens[i:i + 3]) for i in range(max(0, len(tokens) - 2))}
        for old_split, old_shingles in prompts:
            if split != old_split and shingles and old_shingles:
                similarity = len(shingles & old_shingles) / len(shingles | old_shingles)
                if similarity >= 0.8:
                    raise ProjectError("near_duplicate", "Near-duplicate task templates cross split boundaries.")
        prompts.append((split, shingles))
    return {"status": "validated", "records": len(records), "groups": len(groups),
            "split_counts": dict(Counter(r["split"] for r in records)),
            "dataset_sha256": fingerprint(records), "registry_sha256": fingerprint(registry),
            "corpus_id": corpus.snapshot_id, "training_ready": False,
            "limitations": ["Registry attestations are not independent scientific review.",
                            "Lexical near-duplicate scanning does not prove absence of leakage.",
                            "Baseline, benchmark sealing and model compatibility remain pending."]}


def training_subset(records: list[dict]) -> list[dict]:
    """Call only after validating the full dataset; excludes dev and sealed test."""
    return [record for record in records if record["split"] == "train"]
