"""Read-only local evidence audit. Missing prerequisites stay visibly pending."""

from .corpus import Corpus
from .errors import ProjectError
from .parent import parent_manifest
from .provenance import fingerprint, read_json


def audit(config, gates):
    checks = [{"check": "cpu_policy", "status": "pass", "reason": "Training and model downloads disabled by schema."}]
    preflight_path = config.artifacts / "preflight.json"
    if preflight_path.exists():
        report = read_json(preflight_path)
        if isinstance(report, dict) and report.get("config_sha256") == fingerprint(config.values):
            gates[0] = {"gate": "G01", "status": "pass", "reason": "Local CPU preflight matches current config; no GPU work authorized."}
    gates[1]["reason"] = "CPU tools have local test evidence; real training/inference backend readiness remains pending."
    if config.values["corpus"]["path"]:
        try:
            corpus = Corpus.from_config(config)
            checks.append({"check": "corpus_integrity", "status": "pass", "corpus_id": corpus.snapshot_id,
                           "fixture_only": corpus.fixture_only, "coverage": corpus.coverage})
        except ProjectError as exc:
            checks.append({"check": "corpus_integrity", "status": "fail", "reason": exc.code})
    else:
        checks.append({"check": "corpus_integrity", "status": "pending", "reason": "No approved production corpus configured."})
    checks.append({"check": "model_revision_pins", "status": "pass" if all(row["revision"] for row in config.values["models"].values()) else "pending",
                   "reason": "Revision metadata does not prove trainability or effective-base reconstruction."})
    parent = parent_manifest()
    checks.append({"check": "parent_contract", "status": "pass", "commit": parent["commit"],
                   "version": parent["version"], "manifest_sha256": fingerprint(parent),
                   "reason": "Pinned inspection snapshot only; no live parent refresh was performed."})
    ledger_path = config.artifacts / "implementation/ledger.json"
    if ledger_path.exists():
        try:
            ledger = read_json(ledger_path)
            if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
                raise ProjectError("ledger_shape", "Invalid ledger.")
            for item in ledger["entries"]:
                if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
                    raise ProjectError("ledger_shape", "Invalid ledger entry.")
                identity = item["sha256"]
                if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
                    raise ProjectError("ledger_hash", "Invalid ledger hash.")
                entry = read_json(ledger_path.parent / (identity + ".json"))
                if fingerprint(entry) != identity or entry != {k: v for k, v in item.items() if k != "sha256"}:
                    raise ProjectError("ledger_hash", "Historical evidence changed.")
            checks.append({"check": "ledger_integrity", "status": "pass", "entries": len(ledger["entries"])})
        except ProjectError as exc:
            checks.append({"check": "ledger_integrity", "status": "fail", "reason": exc.code})
    else:
        checks.append({"check": "ledger_integrity", "status": "pending", "reason": "Run preflight/CPU checks to create evidence."})
    return {"status": "fail" if any(c["status"] == "fail" for c in checks) else "pending",
            "checks": checks, "gates": gates, "trained_candidate": False,
            "release_qualified": False, "mutations": False}
